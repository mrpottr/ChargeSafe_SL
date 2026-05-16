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


# This function filters out sensitive information from dictionaries like headers or query parameters before logging. 
# It is built using a simple dictionary comprehension that checks keys against a predefined list of sensitive terms, 
# replacing any matching values with a '[redacted]' placeholder to prevent credential leaks.
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


# This function extracts relevant metadata from an incoming HTTP request for use in error logs. 
# It is built by pulling out the HTTP method, URL path, client IP, and safely sanitizing 
# the headers and query parameters to provide a comprehensive debugging snapshot.
def _request_context(request: Request) -> dict:
    client_host = request.client.host if request.client else "unknown"
    return {
        "method": request.method,
        "path": request.url.path,
        "query_params": _sanitize_mapping(dict(request.query_params)),
        "headers": _sanitize_mapping(dict(request.headers)),
        "client_ip": client_host,
    }


# This function determines whether to show a detailed error message or a generic one based on the environment. 
# It is built using a simple conditional check against the application's configuration, ensuring that 
# verbose technical details are only exposed during local development, never in production.
def _production_safe_detail(default_message: str, original_detail) -> str:
    if not settings.is_production:
        if isinstance(original_detail, str):
            return original_detail
        return default_message
    return default_message


# This function intercepts intentional HTTP exceptions thrown by the application code, like a 404 or 401 error. 
# It is built as a FastAPI exception handler that securely logs the request context and the error detail, 
# then standardizes the JSON response returned to the client.
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


# This function catches errors that occur when a client sends an invalid or malformed payload. 
# It is built to log the specific validation failures securely, then return a 422 Unprocessable Entity 
# response that hides exact payload details if the system is running in production.
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


# This function acts as the ultimate safety net, catching any unexpected crashes or bugs in the application. 
# It is built to generate a unique error ID, log the full traceback alongside the sanitized request context, 
# and return a generic 500 Internal Server Error to the user without exposing the underlying code issue.
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
