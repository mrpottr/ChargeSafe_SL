import json
import logging
from datetime import datetime, timezone

from app.core.config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        extra_data = getattr(record, "extra_data", None)
        if isinstance(extra_data, dict):
            payload.update(extra_data)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    root_logger = logging.getLogger()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    if root_logger.handlers:
        for handler in root_logger.handlers:
            handler.setFormatter(JsonFormatter())
        root_logger.setLevel(log_level)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)
