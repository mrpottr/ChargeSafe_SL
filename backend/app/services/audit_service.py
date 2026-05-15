import json
import logging
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.models import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    @staticmethod
    def build_request_context(request) -> dict[str, Any]:
        client_ip = request.client.host if request.client else None
        return {
            "ip_address": client_ip,
            "user_agent": request.headers.get("user-agent"),
        }

    @staticmethod
    def _serialize_details(details: Any) -> str | None:
        if details is None:
            return None
        if isinstance(details, str):
            return details
        return json.dumps(details, default=str)

    @staticmethod
    def log_event(
        *,
        action_type: str,
        result: str,
        user_id=None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: Any = None,
    ) -> AuditLog:
        return AuditLog(
            action_type=action_type,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            result=result,
            details=AuditService._serialize_details(details),
        )

    @staticmethod
    def log_event_safely(_db, **kwargs) -> None:
        audit_db = SessionLocal()
        try:
            # Keep audit logging isolated so auth and other user flows succeed
            # even if audit persistence fails because of legacy schema drift.
            audit_db.add(AuditService.log_event(**kwargs))
            audit_db.commit()
        except SQLAlchemyError:
            logger.exception("Failed to persist audit log event")
            audit_db.rollback()
        except Exception:
            logger.exception("Failed to enqueue audit log event")
            audit_db.rollback()
        finally:
            audit_db.close()
