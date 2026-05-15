from sqlalchemy import Column, DateTime, String, Float, Integer, Boolean, Text, UUID, func, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid

Base = declarative_base()


def enum_values(enum_cls):
    return [member.value for member in enum_cls]


class UserRole(str, enum.Enum):
    admin = "admin"
    standard_user = "standard_user"


class StationStatus(str, enum.Enum):
    operational = "operational"
    faulty = "faulty"
    offline = "offline"
    unknown = "unknown"
    maintenance = "maintenance"


class CyberRiskLevel(str, enum.Enum):
    low = "LOW"
    medium = "MEDIUM"
    high = "HIGH"
    critical = "CRITICAL"


class IncidentType(str, enum.Enum):
    overheating = "Overheating"
    billing_error = "Billing Error"
    network_outage = "Network Outage"
    connector_damage = "Connector Damage"
    firmware_issue = "Firmware Issue"
    power_fluctuation = "Power Fluctuation"
    authentication_failure = "Authentication Failure"
    positive = "Positive"
    other = "Other"


class ReportStatus(str, enum.Enum):
    pending = "PENDING"
    under_review = "UNDER REVIEW"
    flagged = "FLAGGED"
    resolved = "RESOLVED"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.standard_user, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)
    email_verified = Column(Boolean, default=True, nullable=False)
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    mfa_secret = Column(Text, nullable=True)
    mfa_pending_secret = Column(Text, nullable=True)

    reports = relationship("Report", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    messages = relationship("Message", back_populates="user")
    settings = relationship("UserSettings", back_populates="user", uselist=False)
    audit_logs = relationship("AuditLog", back_populates="user")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")


class ChargingStation(Base):
    __tablename__ = "charging_stations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    operator = Column(String(255), nullable=True)
    connector_types = Column(String(255), nullable=True)
    charging_power_kw = Column(Float, nullable=True)
    status = Column(Enum(StationStatus), default=StationStatus.unknown, nullable=False, index=True)
    safety_score = Column(Float, nullable=True)  # Stored as risk score from 0-100
    cyber_risk_level = Column(
        Enum(CyberRiskLevel, values_callable=enum_values),
        nullable=True,
    )
    firmware_version = Column(String(50), nullable=True)
    firmware_age_days = Column(Integer, nullable=True)
    temperature_celsius = Column(Float, nullable=True)
    power_status = Column(String(50), nullable=True)  # e.g., "Stable", "Fluctuation", "Unstable"
    fault_count = Column(Integer, default=0)
    last_scored_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    reports = relationship("Report", back_populates="station")
    score_history = relationship("ScoreHistory", back_populates="station", cascade="all, delete-orphan")
    temperature_history = relationship("TemperatureHistory", back_populates="station", cascade="all, delete-orphan")
    cyber_scores = relationship("CyberScore", back_populates="station", cascade="all, delete-orphan")

    @property
    def risk_score(self):
        return self.safety_score

    @property
    def risk_level(self):
        score = self.safety_score if self.safety_score is not None else 0
        if score <= 30:
            return "LOW"
        if score <= 70:
            return "MEDIUM"
        return "HIGH"


class CyberCriterion(Base):
    __tablename__ = "cyber_criteria"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    criterion_name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    iec_reference = Column(Text, nullable=True)
    weight = Column(Float, nullable=False)
    score_low = Column(Integer, default=0)
    score_medium = Column(Integer, default=2)
    score_high = Column(Integer, default=4)

    cyber_scores = relationship("CyberScore", back_populates="criterion")


class CyberScore(Base):
    __tablename__ = "cyber_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    station_id = Column(UUID(as_uuid=True), ForeignKey("charging_stations.id"), nullable=False, index=True)
    criterion_id = Column(UUID(as_uuid=True), ForeignKey("cyber_criteria.id"), nullable=False, index=True)
    score_value = Column(Integer, nullable=False)
    risk_rating = Column(
        Enum(CyberRiskLevel, values_callable=enum_values),
        nullable=True,
    )
    evaluated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    notes = Column(Text, nullable=True)

    station = relationship("ChargingStation", back_populates="cyber_scores")
    criterion = relationship("CyberCriterion", back_populates="cyber_scores")



class Report(Base):
    __tablename__ = "incident_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    station_id = Column(UUID(as_uuid=True), ForeignKey("charging_stations.id"), nullable=False, index=True)
    report_type = Column(Enum(IncidentType), nullable=False)
    severity = Column(Integer)  # 1-5, higher is worse
    description = Column(Text, nullable=False)
    status = Column(
        Enum(ReportStatus, values_callable=enum_values),
        default=ReportStatus.resolved,
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="reports")
    station = relationship("ChargingStation", back_populates="reports")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(String(50), nullable=False)  # 'danger', 'warn', 'info', 'success'
    icon = Column(String(10), nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="notifications")


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(10), nullable=False)  # 'user' or 'bot'
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="messages")


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False, index=True)
    push_notifications_enabled = Column(Boolean, default=True)
    alert_threshold = Column(Integer, default=70)  # Risk score threshold for alerts
    units_system = Column(String(50), default="Metric (°C, km)")
    language = Column(String(50), default="English")
    map_pin_color_mode = Column(String(100), default="Risk Score (Green/Amber/Red)")
    safe_threshold = Column(Integer, default=30)
    warning_threshold = Column(Integer, default=70)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="settings")


class ScoreHistory(Base):
    __tablename__ = "score_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    station_id = Column(UUID(as_uuid=True), ForeignKey("charging_stations.id"), nullable=False, index=True)
    score = Column(Float, nullable=False)
    level = Column(String(20), nullable=False)  # 'LOW', 'MEDIUM', 'HIGH'
    trigger = Column(String(50), nullable=False)  # 'System', 'Auto', 'Manual'
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    station = relationship("ChargingStation", back_populates="score_history")


class TemperatureHistory(Base):
    __tablename__ = "temperature_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    station_id = Column(UUID(as_uuid=True), ForeignKey("charging_stations.id"), nullable=False, index=True)
    temperature_celsius = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    station = relationship("ChargingStation", back_populates="temperature_history")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action_type = Column(String(100), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    result = Column(String(20), nullable=False, index=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = relationship("User", back_populates="audit_logs")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    refresh_token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True, index=True)
    revoke_reason = Column(String(100), nullable=True)
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="sessions")
