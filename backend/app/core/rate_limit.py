from collections import defaultdict, deque
from hashlib import sha256
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


limiter = Limiter(key_func=get_remote_address, headers_enabled=False)


class ApiRateLimitMiddleware(BaseHTTPMiddleware):
    """Apply a lightweight in-memory rate limit to every API route."""

    # This function sets up the in-memory rate limiting middleware when the application starts. 
    # It is built by initializing a thread-safe lock and a tracking dictionary that 
    # uses double-ended queues to keep track of recent request timestamps for each client.
    def __init__(self, app):
        super().__init__(app)
        self._request_log: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    # This function determines how to uniquely identify the source of an incoming request for rate limiting. 
    # It is built by first looking for an authorization token hash to identify logged-in users, 
    # and safely falls back to the client's IP address for unauthenticated requests.
    @staticmethod
    def _client_key(request: Request) -> str:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token_hash = sha256(auth_header.removeprefix("Bearer ").encode("utf-8")).hexdigest()[:16]
            return f"token:{token_hash}"

        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}"

    # This function decides the maximum number of requests allowed per minute based on the route being accessed. 
    # It is built using simple string matching to enforce stricter limits on sensitive endpoints 
    # like authentication, while applying a broader limit for general API traffic.
    @staticmethod
    def _limit_for_path(path: str) -> int:
        if path.startswith("/api/auth/"):
            return settings.auth_rate_limit_per_minute
        return settings.api_rate_limit_per_minute

    # This function checks if a client has exceeded their allowed request quota within a given time window. 
    # It is built using a sliding window algorithm that removes expired timestamps and 
    # uses a thread lock to safely calculate whether to accept the request or enforce a cooldown.
    def _consume_slot(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        import time

        now = time.time()
        retry_after = 0

        with self._lock:
            hits = self._request_log[key]
            while hits and now - hits[0] >= window_seconds:
                hits.popleft()

            if len(hits) >= limit:
                retry_after = max(1, int(window_seconds - (now - hits[0])) + 1)
                return False, retry_after

            hits.append(now)
            return True, retry_after

    # This function intercepts every HTTP request to enforce the rate limiting policy before it reaches the core application. 
    # It is built to bypass non-API paths, compute the specific limit for the requested endpoint, 
    # and either reject traffic with a 429 status or allow it to proceed seamlessly.
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        rate_limit = self._limit_for_path(path)
        rate_key = f"{self._client_key(request)}:{request.method}:{path}"
        allowed, retry_after = self._consume_slot(rate_key, rate_limit, 60)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Please wait {retry_after} seconds and try again.",
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)

__all__ = [
    "ApiRateLimitMiddleware",
    "RateLimitExceeded",
    "_rate_limit_exceeded_handler",
    "limiter",
]
