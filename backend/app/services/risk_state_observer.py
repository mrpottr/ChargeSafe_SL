from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import ChargingStation, Notification, User


LOW_RISK_MAX = 30.0
MEDIUM_RISK_MAX = 70.0


# These formatting helpers keep risk-change messaging consistent everywhere the
# backend needs to notify users about rescoring events.
def map_risk_category(score: Optional[float]) -> Optional[str]:
    """Map a numeric score into the app's existing LOW / MEDIUM / HIGH bands."""
    if score is None:
        return None
    if score <= LOW_RISK_MAX:
        return "LOW"
    if score <= MEDIUM_RISK_MAX:
        return "MEDIUM"
    return "HIGH"


def build_state_change_message(station_name: str, old_category: str, new_category: str) -> str:
    return f"Charging Station {station_name} has changed from {old_category} to {new_category}."


def build_score_update_message(station_name: str, old_score: float, new_score: float, category: str) -> str:
    return (
        f"Charging Station {station_name} risk score changed from "
        f"{old_score:.1f} to {new_score:.1f} and is currently {category}."
    )


def _get_notification_style(category: str) -> tuple[str, str]:
    if category == "HIGH":
        return "danger", "🚨"
    if category == "MEDIUM":
        return "warn", "⚠️"
    return "success", "✅"


def notify_on_risk_state_change(
    db: Session,
    *,
    station_id,
    old_score: Optional[float],
    new_score: Optional[float],
    timestamp: datetime,
) -> int:
    # Notification fan-out happens only after the score meaningfully changes, so
    # users see state transitions and repeated rescoring without duplicate noise.
    """
    Insert user notifications when a station's ML score changes after the first score.

    Category crossings keep the stronger state-change message. Same-band score changes
    still notify so the UI can reflect repeated feedback-driven rescoring events.
    """
    old_category = map_risk_category(old_score)
    new_category = map_risk_category(new_score)
    if old_category is None or new_category is None:
        return 0
    if round(float(old_score), 1) == round(float(new_score), 1):
        return 0

    station = db.query(ChargingStation).filter(ChargingStation.id == station_id).first()
    station_label = station.name if station else str(station_id)
    if old_category == new_category:
        title = f"Risk Score Updated - {station_label}"
        message = build_score_update_message(
            station_label,
            float(old_score),
            float(new_score),
            new_category,
        )
    else:
        title = f"Risk State Change - {station_label}"
        message = build_state_change_message(station_label, old_category, new_category)
    notification_type, icon = _get_notification_style(new_category)

    recipients = db.query(User).filter(User.is_active == True).all()  # noqa: E712
    created = 0

    for user in recipients:
        if user.settings and user.settings.push_notifications_enabled is False:
            continue

        existing = (
            db.query(Notification)
            .filter(
                Notification.user_id == user.id,
                Notification.title == title,
                Notification.message == message,
                Notification.created_at == timestamp,
            )
            .first()
        )
        if existing:
            continue

        db.add(
            Notification(
                user_id=user.id,
                title=title,
                message=message,
                notification_type=notification_type,
                icon=icon,
                created_at=timestamp,
            )
        )
        created += 1

    return created
