from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pyotp
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    ChargingStation,
    CyberCriterion,
    CyberRiskLevel,
    IncidentType,
    Message,
    Notification,
    Report,
    ReportStatus,
    ScoreHistory,
    StationStatus,
    TemperatureHistory,
    User,
    UserRole,
    UserSettings,
)
from app.services.session_service import SessionService


DEFAULT_PASSWORD = "StrongPass1"


def unique_value(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def create_user(
    db: Session,
    *,
    username: str | None = None,
    email: str | None = None,
    password: str = DEFAULT_PASSWORD,
    role: UserRole = UserRole.standard_user,
    is_active: bool = True,
    email_verified: bool = True,
    mfa_enabled: bool = True,
    mfa_secret: str | None = None,
    mfa_pending_secret: str | None = None,
    create_settings: bool = True,
) -> User:
    username = username or unique_value("user")
    email = email or f"{username}@example.com"

    if mfa_enabled and not mfa_secret:
        mfa_secret = pyotp.random_base32()

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
        email_verified=email_verified,
        mfa_enabled=mfa_enabled,
        mfa_secret=mfa_secret,
        mfa_pending_secret=mfa_pending_secret,
    )
    db.add(user)
    db.flush()

    if create_settings:
        db.add(UserSettings(user_id=user.id))
        db.flush()

    db.commit()
    db.refresh(user)
    setattr(user, "_plain_password", password)
    return user


def create_station(
    db: Session,
    *,
    name: str | None = None,
    city: str = "Colombo",
    status: StationStatus = StationStatus.operational,
    risk_score: float = 55.0,
    latitude: float = 6.9271,
    longitude: float = 79.8612,
    operator: str = "ChargeSafe",
    connector_types: str = "CCS2",
    charging_power_kw: float = 60.0,
    temperature_celsius: float = 33.0,
    fault_count: int = 0,
) -> ChargingStation:
    station = ChargingStation(
        name=name or unique_value("station"),
        latitude=latitude + (uuid4().int % 1000) / 100000,
        longitude=longitude + (uuid4().int % 1000) / 100000,
        city=city,
        address=f"{city} test address",
        operator=operator,
        connector_types=connector_types,
        charging_power_kw=charging_power_kw,
        status=status,
        safety_score=risk_score,
        cyber_risk_level=_cyber_level_for_score(risk_score),
        temperature_celsius=temperature_celsius,
        power_status="Stable",
        fault_count=fault_count,
        last_scored_at=datetime.utcnow(),
    )
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


def create_score_history(
    db: Session,
    station_id,
    *,
    score: float,
    level: str,
    trigger: str,
    recorded_at: datetime,
) -> ScoreHistory:
    item = ScoreHistory(
        station_id=station_id,
        score=score,
        level=level,
        trigger=trigger,
        recorded_at=recorded_at,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def create_temperature_history(
    db: Session,
    station_id,
    *,
    temperature_celsius: float,
    recorded_at: datetime,
) -> TemperatureHistory:
    item = TemperatureHistory(
        station_id=station_id,
        temperature_celsius=temperature_celsius,
        recorded_at=recorded_at,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def create_report(
    db: Session,
    *,
    user_id,
    station_id,
    report_type: IncidentType = IncidentType.overheating,
    severity: int | None = 4,
    description: str = "Integration test incident description.",
    status: ReportStatus = ReportStatus.resolved,
) -> Report:
    report = Report(
        user_id=user_id,
        station_id=station_id,
        report_type=report_type,
        severity=severity,
        description=description,
        status=status,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def create_notification(
    db: Session,
    *,
    user_id,
    title: str = "Test notification",
    message: str = "Test notification body",
    notification_type: str = "info",
    is_read: bool = False,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        icon="i",
        is_read=is_read,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def create_message(
    db: Session,
    *,
    user_id,
    role: str,
    text: str,
) -> Message:
    message = Message(user_id=user_id, role=role, text=text)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def create_cyber_criterion(
    db: Session,
    *,
    criterion_name: str,
    weight: float,
    description: str = "Test criterion",
    iec_reference: str = "IEC-TEST",
) -> CyberCriterion:
    criterion = CyberCriterion(
        criterion_name=criterion_name,
        description=description,
        iec_reference=iec_reference,
        weight=weight,
    )
    db.add(criterion)
    db.commit()
    db.refresh(criterion)
    return criterion


def create_authenticated_session(db: Session, user: User) -> tuple[str, str]:
    access_token, refresh_token, _session = SessionService.create_session(
        db,
        user,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    db.commit()
    return access_token, refresh_token


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def current_totp(secret: str) -> str:
    return pyotp.TOTP(secret).now()


def _cyber_level_for_score(score: float) -> CyberRiskLevel:
    if score <= 30:
        return CyberRiskLevel.low
    if score <= 70:
        return CyberRiskLevel.medium
    return CyberRiskLevel.high
