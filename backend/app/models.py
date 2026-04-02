from sqlalchemy import Column, DateTime, String, Float, Integer, Boolean, Text, UUID, func, Enum, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid

Base = declarative_base()


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

    reports = relationship("Report", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    messages = relationship("Message", back_populates="user")
    settings = relationship("UserSettings", back_populates="user", uselist=False)


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
    safety_score = Column(Float, nullable=True)  # 0-100
    cyber_risk_level = Column(Enum(CyberRiskLevel), nullable=True)
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


class Report(Base):
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    station_id = Column(UUID(as_uuid=True), ForeignKey("charging_stations.id"), nullable=False, index=True)
    report_type = Column(Enum(IncidentType), nullable=False)
    severity = Column(Integer)  # 1-5, higher is worse
    description = Column(Text, nullable=False)
    status = Column(Enum(ReportStatus), default=ReportStatus.pending, nullable=False, index=True)
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
    alert_threshold = Column(Integer, default=50)  # Safety score threshold for alerts
    units_system = Column(String(50), default="Metric (°C, km)")
    language = Column(String(50), default="English")
    map_pin_color_mode = Column(String(100), default="Risk Score (Green/Amber/Red)")
    safe_threshold = Column(Integer, default=75)
    warning_threshold = Column(Integer, default=50)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="settings")


class ScoreHistory(Base):
    __tablename__ = "score_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    station_id = Column(UUID(as_uuid=True), ForeignKey("charging_stations.id"), nullable=False, index=True)
    score = Column(Float, nullable=False)
    level = Column(String(20), nullable=False)  # 'SAFE', 'WARN', 'CRIT'
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
