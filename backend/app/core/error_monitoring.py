import logging
import time
from collections import deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)


class ErrorRateMonitoringMiddleware(BaseHTTPMiddleware):
    """Track recent 5xx responses and log when error rates spike."""

    def __init__(self, app):
        super().__init__(app)
        self._errors = deque()
        self._lock = Lock()

    def _record_error(self, now: float) -> int:
        with self._lock:
            self._errors.append(now)
            while self._errors and now - self._errors[0] > settings.error_rate_window_seconds:
                self._errors.popleft()
            return len(self._errors)

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if response.status_code >= 500:
            current_count = self._record_error(time.time())
            if current_count >= settings.error_rate_threshold:
                logger.warning(
                    "Error rate threshold exceeded",
                    extra={
                        "extra_data": {
                            "path": request.url.path,
                            "status_code": response.status_code,
                            "error_count": current_count,
                            "window_seconds": settings.error_rate_window_seconds,
                        }
                    },
                )
        return response
