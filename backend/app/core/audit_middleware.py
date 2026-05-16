from app.core.security import decode_token
from app.db.session import SessionLocal
from app.services.audit_service import AuditService


SENSITIVE_PATH_PREFIXES = (
    "/api/auth/mfa/",
    "/api/me/change-password",
    "/api/me/delete",
    "/api/admin/",
    "/api/sync-openchargemap",
    "/api/internal/process-new-feedback",
    "/api/chat",
)


# This function checks if an incoming API request targets a high-risk or sensitive endpoint. 
# It is built by iterating through a predefined list of sensitive path prefixes and returning 
# true if the current request's path matches any of them.
def _is_sensitive_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in SENSITIVE_PATH_PREFIXES)


class AuditMiddleware:
    # This function initializes the audit logging middleware when the application starts. 
    # It is built simply by storing a reference to the main ASGI application so that 
    # incoming requests can be passed down the middleware chain.
    def __init__(self, app):
        self.app = app

    # This function intercepts incoming HTTP requests to silently log activities on sensitive endpoints. 
    # It is built using the ASGI specification to wrap the response, extract user identity from the JWT, 
    # and securely record the event details into the database via the AuditService.
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")
        if not _is_sensitive_path(path):
            await self.app(scope, receive, send)
            return

        response_status = {"code": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                response_status["code"] = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)

        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
        authorization = headers.get("authorization", "")
        user_id = None
        if authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
            try:
                user_id = decode_token(token).get("user_id")
            except Exception:
                user_id = None

        client = scope.get("client")
        ip_address = client[0] if client else None
        user_agent = headers.get("user-agent")

        db = SessionLocal()
        try:
            AuditService.log_event_safely(
                db,
                action_type="sensitive_api_call",
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                result="success" if response_status["code"] < 400 else "failure",
                details={
                    "path": path,
                    "method": method,
                    "status_code": response_status["code"],
                },
            )
        except Exception:
            pass
        finally:
            db.close()
