import secrets

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


# These small request inspectors let the middleware distinguish browser cookie
# flows from bearer-token API traffic before it applies any CSRF checks.
def _request_has_non_csrf_cookies(request) -> bool:
    cookie_names = {name.strip() for name in request.cookies.keys() if name.strip()}
    if not cookie_names:
        return False
    return any(cookie_name.lower() != settings.csrf_cookie_name.lower() for cookie_name in cookie_names)


def _uses_bearer_auth(request) -> bool:
    authorization = request.headers.get("authorization", "")
    return authorization.lower().startswith("bearer ")


def _origin_is_allowed(request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        referer = request.headers.get("referer", "")
        return any(referer.startswith(allowed_origin) for allowed_origin in settings.backend_cors_origins)
    return origin in settings.backend_cors_origins


class CSRFMiddleware(BaseHTTPMiddleware):
    # The middleware only steps in for state-changing browser requests, which
    # keeps the API token flows simple while still protecting cookie sessions.
    """Protect cookie-backed state-changing requests without affecting bearer-token APIs."""

    async def dispatch(self, request, call_next):
        csrf_cookie = request.cookies.get(settings.csrf_cookie_name)

        if request.method not in SAFE_METHODS and _request_has_non_csrf_cookies(request) and not _uses_bearer_auth(request):
            csrf_header = request.headers.get(settings.csrf_header_name, "")

            if not _origin_is_allowed(request):
                return JSONResponse(status_code=403, content={"detail": "CSRF origin check failed"})

            if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
                return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})

        response = await call_next(request)

        if not csrf_cookie:
            response.set_cookie(
                key=settings.csrf_cookie_name,
                value=secrets.token_urlsafe(32),
                secure=settings.should_enforce_https,
                httponly=False,
                samesite="lax",
                path="/",
            )

        return response
