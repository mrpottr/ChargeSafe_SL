import logging
from uuid import uuid4

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.error_tracking import capture_exception

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "password",
    "current_password",
    "new_password",
    "token",
    "secret",
    "code",
}


def _sanitize_mapping(mapping: dict | None) -> dict:
    if not isinstance(mapping, dict):
        return {}

    sanitized = {}
    for key, value in mapping.items():
        if str(key).lower() in SENSITIVE_KEYS:
            sanitized[key] = "[redacted]"
        else:
            sanitized[key] = value
    return sanitized


def _request_context(request: Request) -> dict:
    client_host = request.client.host if request.client else "unknown"
    return {
        "method": request.method,
        "path": request.url.path,
        "query_params": _sanitize_mapping(dict(request.query_params)),
        "headers": _sanitize_mapping(dict(request.headers)),
        "client_ip": client_host,
    }


def _production_safe_detail(default_message: str, original_detail) -> str:
    if not settings.is_production:
        if isinstance(original_detail, str):
            return original_detail
        return default_message
    return default_message


async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning(
        "HTTP exception",
        extra={
            "extra_data": {
                "status_code": exc.status_code,
                "detail": _production_safe_detail("Request failed", exc.detail),
                **_request_context(request),
            }
        },
    )

    detail = exc.detail
    if settings.is_production and exc.status_code >= 500:
        detail = "An internal server error occurred."

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail},
        headers=exc.headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "Request validation failed",
        extra={
            "extra_data": {
                "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "errors": exc.errors() if not settings.is_production else "[redacted]",
                **_request_context(request),
            }
        },
    )

    detail = exc.errors() if not settings.is_production else "Invalid request payload."
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": detail},
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    error_id = str(uuid4())

    logger.exception(
        "Unhandled application exception",
        extra={
            "extra_data": {
                "error_id": error_id,
                **_request_context(request),
            }
        },
    )
    capture_exception(exc)

    detail = str(exc) if not settings.is_production else "An internal server error occurred."
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": detail, "error_id": error_id},
    )
