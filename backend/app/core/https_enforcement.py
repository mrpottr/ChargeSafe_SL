from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


def is_request_secure(request) -> bool:
    # Security decisions need to work in both local direct traffic and proxy
    # deployments, so this helper checks the URL scheme and forwarded headers.
    if request.url.scheme == "https":
        return True

    if settings.trust_x_forwarded_proto:
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        if forwarded_proto.split(",")[0].strip().lower() == "https":
            return True

    return False


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    # Redirecting here keeps HTTPS enforcement transparent to route handlers, so
    # individual endpoints do not need to know whether transport is secure.
    """Redirect insecure requests to HTTPS when enforcement is enabled."""

    async def dispatch(self, request, call_next):
        if settings.should_enforce_https and not is_request_secure(request):
            https_url = str(request.url.replace(scheme="https"))
            return RedirectResponse(url=https_url, status_code=307)

        return await call_next(request)
