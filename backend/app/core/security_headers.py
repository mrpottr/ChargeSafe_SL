from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.https_enforcement import is_request_secure


API_CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        "object-src 'none'",
    ]
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    # Response hardening lives in middleware so the app can stamp consistent
    # headers and cookie flags across every route without touching handlers.
    """Attach security headers without changing application logic."""

    @staticmethod
    def _cookie_name(cookie_value: str) -> str:
        return cookie_value.split("=", 1)[0].strip().lower()

    @staticmethod
    def _secure_cookie_header(cookie_value: str) -> str:
        lowered = cookie_value.lower()
        updated_value = cookie_value
        cookie_name = SecurityHeadersMiddleware._cookie_name(cookie_value)

        if "secure" not in lowered:
            updated_value = f"{updated_value}; Secure"
        if cookie_name != settings.csrf_cookie_name.lower() and "httponly" not in lowered:
            updated_value = f"{updated_value}; HttpOnly"
        if "samesite=" not in lowered:
            updated_value = f"{updated_value}; SameSite=Lax"

        return updated_value

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        response.headers["Content-Security-Policy"] = API_CONTENT_SECURITY_POLICY
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "no-referrer"

        if settings.should_enforce_https and is_request_secure(request):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        if settings.is_production:
            updated_headers = []
            for header_name, header_value in response.raw_headers:
                if header_name.lower() == b"set-cookie":
                    secured_cookie = self._secure_cookie_header(header_value.decode("latin-1"))
                    updated_headers.append((header_name, secured_cookie.encode("latin-1")))
                else:
                    updated_headers.append((header_name, header_value))
            response.raw_headers = updated_headers

        return response
