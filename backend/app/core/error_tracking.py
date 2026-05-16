import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_sentry_sdk = None


def init_error_tracking() -> None:
    # Error tracking is optional by design so local development can stay light,
    # while production can enable Sentry just by supplying configuration.
    global _sentry_sdk

    if not settings.sentry_dsn:
        return

    try:
        import sentry_sdk  # type: ignore
    except ImportError:
        logger.warning(
            "Sentry DSN is configured but sentry_sdk is not installed",
            extra={"extra_data": {"component": "error_tracking"}},
        )
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=settings.app_version,
        send_default_pii=False,
    )
    _sentry_sdk = sentry_sdk


def capture_exception(exc: Exception) -> None:
    # Runtime code can call this helper freely because it becomes a no-op when
    # external tracking is disabled, which keeps error paths uncomplicated.
    if _sentry_sdk is not None:
        _sentry_sdk.capture_exception(exc)
