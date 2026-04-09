from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime
from uuid import UUID
from app.models import UserRole, StationStatus, CyberRiskLevel, IncidentType, ReportStatus


# ============== User Schemas ==============
class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)

    @field_validator('username')
    def username_alphanumeric(cls, v):
        assert v.isalnum() or '_' in v, 'Username must be alphanumeric or contain underscores'
        return v


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True


class UserDetailResponse(UserResponse):
    failed_login_attempts: int
    locked_until: Optional[datetime]


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=6)


class DeleteAccountRequest(BaseModel):
    current_password: str = Field(..., min_length=6)

# ============== Charging Station Schemas ==============
class StationScoreHistoryItem(BaseModel):
    date: str
    score: float
    level: str
    trigger: str

    class Config:
        from_attributes = True


class ChargingStationResponse(BaseModel):
    id: UUID
    name: str
    latitude: float
    longitude: float
    city: Optional[str]
    address: Optional[str]
    status: StationStatus
    risk_score: Optional[float]
    risk_level: Optional[str]
    cyber_risk_level: Optional[CyberRiskLevel]
    firmware_version: Optional[str]
    firmware_age_days: Optional[int]
    temperature_celsius: Optional[float]
    power_status: Optional[str]
    fault_count: int
    last_scored_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChargingStationDetailResponse(ChargingStationResponse):
    operator: Optional[str]
    connector_types: Optional[str]
    charging_power_kw: Optional[float]


class ChargingStationCreateUpdate(BaseModel):
    name: str = Field(..., min_length=1)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    city: Optional[str] = None
    address: Optional[str] = None
    operator: Optional[str] = None
    status: Optional[StationStatus] = StationStatus.unknown
    risk_score: Optional[float] = Field(None, ge=0, le=100)
    cyber_risk_level: Optional[CyberRiskLevel] = None
    firmware_version: Optional[str] = None
    temperature_celsius: Optional[float] = None
    power_status: Optional[str] = None
    fault_count: int = 0


# ============== Report Schemas ==============
class ReportCreate(BaseModel):
    station_id: UUID
    report_type: IncidentType
    severity: int = Field(..., ge=1, le=5)
    description: str = Field(..., min_length=10)


class ReportUpdate(BaseModel):
    status: ReportStatus


class ReportResponse(BaseModel):
    id: UUID
    user_id: UUID
    station_id: UUID
    report_type: IncidentType
    severity: int
    description: str
    status: ReportStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReportDetailResponse(ReportResponse):
    user: UserResponse
    station: ChargingStationResponse


# ============== Notification Schemas ==============
class NotificationResponse(BaseModel):
    id: UUID
    title: str
    message: str
    notification_type: str
    icon: Optional[str]
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationMarkRead(BaseModel):
    is_read: bool


# ============== Message Schemas ==============
class MessageCreate(BaseModel):
    role: str = Field(..., pattern="^(user|bot)$")
    text: str = Field(..., min_length=1)


class MessageResponse(BaseModel):
    id: UUID
    role: str
    text: str
    created_at: datetime

    class Config:
        from_attributes = True


# ============== Settings Schemas ==============
class UserSettingsResponse(BaseModel):
    id: UUID
    push_notifications_enabled: bool
    alert_threshold: int
    units_system: str
    language: str
    map_pin_color_mode: str
    safe_threshold: int
    warning_threshold: int

    class Config:
        from_attributes = True


class UserSettingsUpdate(BaseModel):
    push_notifications_enabled: Optional[bool] = None
    alert_threshold: Optional[int] = Field(None, ge=0, le=100)
    units_system: Optional[str] = None
    language: Optional[str] = None
    map_pin_color_mode: Optional[str] = None
    safe_threshold: Optional[int] = Field(None, ge=0, le=100)
    warning_threshold: Optional[int] = Field(None, ge=0, le=100)


# ============== Auth Token Schemas ==============
class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class MessageOnlyResponse(BaseModel):
    message: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str

# ============== Score History Schemas ==============
class ScoreHistoryResponse(BaseModel):
    date: str
    score: float
    level: str
    trigger: str

    class Config:
        from_attributes = True
