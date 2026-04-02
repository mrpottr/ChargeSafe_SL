from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from app.db.session import get_db
from app.models import (
    User, ChargingStation, Report, Notification, Message, UserSettings,
    ScoreHistory, TemperatureHistory, UserRole, StationStatus, ReportStatus
)
from app.schemas import (
    UserRegisterRequest, UserLoginRequest, UserResponse, TokenResponse,
    ChangePasswordRequest, DeleteAccountRequest, MessageOnlyResponse,
    ChargingStationResponse, ChargingStationDetailResponse, ChargingStationCreateUpdate,
    ReportCreate, ReportUpdate, ReportResponse, ReportDetailResponse,
    NotificationResponse, NotificationMarkRead,
    MessageCreate, MessageResponse,
    UserSettingsResponse, UserSettingsUpdate
)
from app.core.security import (
    hash_password, verify_password, create_access_token,
    get_current_user, get_current_admin
)

router = APIRouter()


# ============== Health Checks ==============
@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    """Readiness check endpoint."""
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


# ============== Authentication ==============
@router.post("/auth/register", response_model=UserResponse)
def register(request: UserRegisterRequest, db: Session = Depends(get_db)):
    """Register a new user."""
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    existing_username = db.query(User).filter(User.username == request.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Create new user
    user = User(
        username=request.username,
        email=request.email,
        password_hash=hash_password(request.password)
    )
    db.add(user)
    db.flush()
    
    # Create default settings for user
    settings = UserSettings(user_id=user.id)
    db.add(settings)
    
    db.commit()
    db.refresh(user)
    return user


@router.post("/auth/login", response_model=TokenResponse)
def login(request: UserLoginRequest, db: Session = Depends(get_db)):
    """Login user and return JWT token."""
    user = db.query(User).filter(User.email == request.email).first()
    
    if not user or not verify_password(request.password, user.password_hash):
        # Increment failed login attempts
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.now(timezone.utc) + timedelta(hours=1)
            db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Check if account is locked
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is temporarily locked. Try again later."
        )
    
    # Reset failed login attempts on successful login
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    
    # Generate token
    access_token = create_access_token(str(user.id))
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(user)
    }


# ============== Stations ==============
@router.get("/stations", response_model=List[ChargingStationResponse])
def list_stations(
    db: Session = Depends(get_db),
    city: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None),
    max_score: Optional[float] = Query(None),
    limit: int = Query(50, le=100)
):
    """List all charging stations with optional filters."""
    query = db.query(ChargingStation)
    
    if city:
        query = query.filter(ChargingStation.city.ilike(f"%{city}%"))
    
    if status_filter:
        query = query.filter(ChargingStation.status == status_filter)
    
    if min_score is not None:
        query = query.filter(ChargingStation.safety_score >= min_score)
    
    if max_score is not None:
        query = query.filter(ChargingStation.safety_score <= max_score)
    
    stations = query.order_by(ChargingStation.updated_at.desc()).limit(limit).all()
    return stations


@router.get("/stations/{station_id}", response_model=ChargingStationDetailResponse)
def get_station(station_id: UUID, db: Session = Depends(get_db)):
    """Get a specific charging station."""
    station = db.query(ChargingStation).filter(ChargingStation.id == station_id).first()
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Station not found"
        )
    return station


@router.post("/stations", response_model=ChargingStationDetailResponse)
def create_station(
    request: ChargingStationCreateUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Create a new charging station (admin only)."""
    station = ChargingStation(**request.model_dump())
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


@router.put("/stations/{station_id}", response_model=ChargingStationDetailResponse)
def update_station(
    station_id: UUID,
    request: ChargingStationCreateUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update a charging station (admin only)."""
    station = db.query(ChargingStation).filter(ChargingStation.id == station_id).first()
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Station not found"
        )
    
    for key, value in request.model_dump(exclude_unset=True).items():
        setattr(station, key, value)
    
    station.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(station)
    return station


# ============== Reports ==============
@router.post("/reports", response_model=ReportResponse)
def create_report(
    request: ReportCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new incident report."""
    # Verify station exists
    station = db.query(ChargingStation).filter(ChargingStation.id == request.station_id).first()
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Station not found"
        )
    
    report = Report(
        user_id=current_user.id,
        station_id=request.station_id,
        report_type=request.report_type,
        severity=request.severity,
        description=request.description
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.get("/reports", response_model=List[ReportDetailResponse])
def list_reports(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status_filter: Optional[str] = Query(None),
    limit: int = Query(50, le=100)
):
    """Get user's reports."""
    query = db.query(Report).filter(Report.user_id == current_user.id)
    
    if status_filter:
        query = query.filter(Report.status == status_filter)
    
    reports = query.order_by(Report.created_at.desc()).limit(limit).all()
    return reports


@router.get("/reports/{report_id}", response_model=ReportDetailResponse)
def get_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific report."""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found"
        )
    
    # Users can only view their own reports, admins can view all
    if current_user.role != UserRole.admin and report.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    return report


@router.put("/reports/{report_id}", response_model=ReportResponse)
def update_report(
    report_id: UUID,
    request: ReportUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update report status (admin only)."""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found"
        )
    
    report.status = request.status
    report.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(report)
    return report


# ============== Notifications ==============
@router.get("/notifications", response_model=List[NotificationResponse])
def list_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    unread_only: bool = Query(False),
    limit: int = Query(50, le=100)
):
    """Get user's notifications."""
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    
    if unread_only:
        query = query.filter(Notification.is_read == False)
    
    notifications = query.order_by(Notification.created_at.desc()).limit(limit).all()
    return notifications


@router.put("/notifications/{notification_id}", response_model=NotificationResponse)
def update_notification(
    notification_id: UUID,
    request: NotificationMarkRead,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark notification as read/unread."""
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    notification.is_read = request.is_read
    db.commit()
    db.refresh(notification)
    return notification


@router.post("/notifications/mark-all-read")
def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark all notifications as read."""
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).update({"is_read": True})
    db.commit()
    return {"message": "All notifications marked as read"}


# ============== Messages (Chat History) ==============
@router.post("/messages", response_model=MessageResponse)
def create_message(
    request: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new message."""
    message = Message(
        user_id=current_user.id,
        role=request.role,
        text=request.text
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.get("/messages", response_model=List[MessageResponse])
def list_messages(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(100, le=500)
):
    """Get user's message history."""
    messages = db.query(Message).filter(
        Message.user_id == current_user.id
    ).order_by(Message.created_at.asc()).limit(limit).all()
    return messages


@router.delete("/messages")
def clear_messages(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Clear message history."""
    db.query(Message).filter(Message.user_id == current_user.id).delete()
    db.commit()
    return {"message": "Message history cleared"}


# ============== User Settings ==============
@router.get("/settings", response_model=UserSettingsResponse)
def get_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user settings."""
    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settings not found"
        )
    return settings


@router.put("/settings", response_model=UserSettingsResponse)
def update_settings(
    request: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user settings."""
    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settings not found"
        )
    
    for key, value in request.model_dump(exclude_unset=True).items():
        setattr(settings, key, value)
    
    settings.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(settings)
    return settings


# ============== User Profile ==============
@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return current_user


@router.put("/me", response_model=UserResponse)
def update_user_profile(
    username: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user profile."""
    if username:
        # Check if username is already taken
        existing = db.query(User).filter(
            User.username == username,
            User.id != current_user.id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
        current_user.username = username

    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/me/change-password", response_model=MessageOnlyResponse)
def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change the current user's password."""
    if not verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="INCORRECT CURRENT PASSWORD"
        )

    if request.current_password == request.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password"
        )

    current_user.password_hash = hash_password(request.new_password)
    current_user.failed_login_attempts = 0
    current_user.locked_until = None
    db.commit()

    return {"message": "Password changed successfully"}


@router.post("/me/delete", response_model=MessageOnlyResponse)
def delete_account(
    request: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete the current user's account and related data."""
    if not verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="INCORRECT CURRENT PASSWORD"
        )

    db.query(Notification).filter(Notification.user_id == current_user.id).delete()
    db.query(Message).filter(Message.user_id == current_user.id).delete()
    db.query(UserSettings).filter(UserSettings.user_id == current_user.id).delete()
    db.query(Report).filter(Report.user_id == current_user.id).delete()
    db.delete(current_user)
    db.commit()

    return {"message": "Account deleted successfully"}


# ============== Admin - Station Management ==============
@router.get("/admin/stations", response_model=List[ChargingStationDetailResponse])
def admin_list_stations(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
    limit: int = Query(100, le=500)
):
    """Get all stations (admin only)."""
    stations = db.query(ChargingStation).order_by(ChargingStation.updated_at.desc()).limit(limit).all()
    return stations


# ============== Admin - Reports Management ==============
@router.get("/admin/reports", response_model=List[ReportDetailResponse])
def admin_list_reports(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
    status_filter: Optional[str] = Query(None),
    limit: int = Query(100, le=500)
):
    """Get all reports (admin only)."""
    query = db.query(Report)
    
    if status_filter:
        query = query.filter(Report.status == status_filter)
    
    reports = query.order_by(Report.created_at.desc()).limit(limit).all()
    return reports


# ============== Admin - Users Management ==============
@router.get("/admin/users", response_model=List[UserResponse])
def admin_list_users(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
    limit: int = Query(100, le=500)
):
    """Get all users (admin only)."""
    users = db.query(User).order_by(User.created_at.desc()).limit(limit).all()
    return users


@router.delete("/admin/users/{user_id}")
def admin_deactivate_user(
    user_id: UUID,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Deactivate a user (admin only)."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate yourself"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.is_active = False
    db.commit()
    return {"message": "User deactivated"}


# ============== Station Score History ==============
@router.get("/stations/{station_id}/score-history")
def get_station_score_history(
    station_id: UUID,
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365)
):
    """Get station's score history for the last N days."""
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    history = db.query(ScoreHistory).filter(
        ScoreHistory.station_id == station_id,
        ScoreHistory.recorded_at >= cutoff_date
    ).order_by(ScoreHistory.recorded_at.asc()).all()
    
    return [
        {
            "date": h.recorded_at.strftime("%Y-%m-%d"),
            "score": h.score,
            "level": h.level,
            "trigger": h.trigger
        }
        for h in history
    ]


@router.get("/stations/{station_id}/temperature-history")
def get_station_temperature_history(
    station_id: UUID,
    db: Session = Depends(get_db),
    days: int = Query(7, ge=1, le=365)
):
    """Get station's temperature history for the last N days."""
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    history = db.query(TemperatureHistory).filter(
        TemperatureHistory.station_id == station_id,
        TemperatureHistory.recorded_at >= cutoff_date
    ).order_by(TemperatureHistory.recorded_at.asc()).all()
    
    return [
        {
            "date": h.recorded_at.strftime("%Y-%m-%d %H:%M:%S"),
            "temperature": h.temperature_celsius
        }
        for h in history
    ]
