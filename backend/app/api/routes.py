from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks, Request, Response
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from app.db.session import get_db
from app.models import (
    User, ChargingStation, Report, Notification, Message, UserSettings,
    ScoreHistory, TemperatureHistory, CyberCriterion, CyberScore,
    UserRole, StationStatus, ReportStatus, CyberRiskLevel
)
from app.schemas import (
    UserRegisterRequest, UserLoginRequest, UserResponse, TokenResponse,
    ChangePasswordRequest, DeleteAccountRequest, ForgotPasswordRequest, ForgotPasswordChallengeResponse, ResetPasswordRequest,
    EmailVerificationRequest, MfaSetupResponse, MfaEnableRequest, MfaLoginRequest,
    RefreshTokenRequest,
    RegistrationMfaSetupRequest, RegistrationMfaSetupResponse, RegistrationMfaCompleteRequest,
    MessageOnlyResponse,
    ChargingStationResponse, ChargingStationDetailResponse, ChargingStationCreateUpdate,
    StationCyberScoreResponse,
    ReportCreate, ReportUpdate, InternalFeedbackProcessRequest, ReportResponse, ReportDetailResponse,
    NotificationResponse, NotificationMarkRead,
    MessageCreate, MessageResponse,
    UserSettingsResponse, UserSettingsUpdate,
    ChatRequest, ChatResponse
)

from app.core.security import (
    hash_password, verify_password, create_password_reset_token, create_email_verification_token,
    create_registration_verification_token,
    create_mfa_login_token, create_mfa_setup_token,
    decode_password_reset_token, decode_email_verification_token, decode_registration_verification_token,
    decode_mfa_login_token, decode_mfa_setup_token, decode_token,
    get_current_user, get_current_admin
)
from app.core.account_lockout import (
    clear_expired_lockout,
    is_account_locked,
    register_failed_login_attempt,
    reset_lockout_state,
)
from app.core.config import settings
from app.core.rate_limit import limiter
from app.services.gemini_chat import generate_chat_reply
from app.services.cyber_scoring_service import CyberScoringService
from app.services.data_loader_service import DataLoaderService
from app.services.email_service import EmailService
from app.services.mfa_service import MfaService
from app.services.risk_state_observer import notify_on_risk_state_change
from app.services.risk_score_ml_service import RiskScoreMLService
from app.services.audit_service import AuditService
from app.services.session_service import SessionService

router = APIRouter()


def write_audit_log(
    db: Session,
    http_request: Request,
    *,
    action_type: str,
    result: str,
    user_id=None,
    details: dict | None = None,
) -> None:
    request_context = AuditService.build_request_context(http_request)
    AuditService.log_event_safely(
        db,
        action_type=action_type,
        result=result,
        user_id=user_id,
        ip_address=request_context["ip_address"],
        user_agent=request_context["user_agent"],
        details=details,
    )


def issue_session_tokens(db: Session, http_request: Request, user: User) -> tuple[str, str]:
    request_context = AuditService.build_request_context(http_request)
    return SessionService.create_session(
        db,
        user,
        ip_address=request_context["ip_address"],
        user_agent=request_context["user_agent"],
    )[:2]


def get_overall_cyber_risk_level(score: float) -> str:
    if score <= 30:
        return "LOW"
    if score <= 70:
        return "MEDIUM"
    if score <= 85:
        return "HIGH"
    return "CRITICAL"



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


@router.post("/sync-openchargemap")
def sync_openchargemap_stations(
    request: Request,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Sync charging stations from OpenChargeMap for Sri Lanka and calculate ML risk scores."""
    stats = DataLoaderService.sync_openchargemap_to_database(db, force_update=True)
    cyber_stats = CyberScoringService.score_all_stations(db)
    write_audit_log(
        db,
        request,
        action_type="admin_sync_openchargemap",
        result="success",
        user_id=current_user.id,
        details={"stats": stats, "cyber_stats": cyber_stats},
    )
    db.commit()
    return {
        "message": "Sync completed",
        "stats": stats,
        "cyber_stats": cyber_stats,
    }


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
def chat_with_ai(
    request: Request,
    response: Response,
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate a chatbot reply using Gemini."""
    try:
        reply = generate_chat_reply(payload.message.strip(), db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service unavailable"
        ) from exc

    return {"reply": reply}


# ============== Authentication ==============
@router.post("/auth/register", response_model=MessageOnlyResponse)
def register(request: UserRegisterRequest, db: Session = Depends(get_db)):
    """Register a new user."""
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user and existing_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    existing_username = db.query(User).filter(User.username == request.username).first()
    if existing_username and existing_username.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )

    if existing_user and not existing_user.email_verified:
        db.query(UserSettings).filter(UserSettings.user_id == existing_user.id).delete()
        db.delete(existing_user)
        db.flush()

    if existing_username and not existing_username.email_verified:
        db.query(UserSettings).filter(UserSettings.user_id == existing_username.id).delete()
        db.delete(existing_username)
        db.flush()

    password_hash = hash_password(request.password)
    verification_token = create_registration_verification_token(
        username=request.username,
        email=request.email,
        password_hash=password_hash,
    )
    verification_link = (
        f"{settings.frontend_base_url}"
        f"?auth=verify-email&token={verification_token}"
    )

    def complete_local_registration_fallback() -> dict:
        user = db.query(User).filter(User.email == request.email).first()
        if user:
            user.username = request.username
            user.password_hash = password_hash
            user.email_verified = True
        else:
            user = User(
                username=request.username,
                email=request.email,
                password_hash=password_hash,
                email_verified=True,
            )
            db.add(user)
            db.flush()

        if not db.query(UserSettings).filter(UserSettings.user_id == user.id).first():
            db.add(UserSettings(user_id=user.id))

        if not user.mfa_pending_secret:
            user.mfa_pending_secret = MfaService.generate_secret()

        db.commit()
        return {
            "message": "Account created. Continue with Microsoft Authenticator setup.",
            "next_step": "mfa_setup",
            "setup_token": create_mfa_setup_token(str(user.id)),
        }

    if not settings.is_production and not EmailService.is_configured():
        return complete_local_registration_fallback()

    try:
        EmailService.send_email_verification_email(request.email, verification_link)
    except ValueError as exc:
        db.rollback()
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Verification email is not configured on the server"
            ) from exc
        return complete_local_registration_fallback()
    except Exception as exc:
        db.rollback()
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Unable to send verification email right now"
            ) from exc
        return complete_local_registration_fallback()

    return {"message": "Verification email sent. Please verify your email before first access."}


@router.post("/auth/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, response: Response, payload: UserLoginRequest, db: Session = Depends(get_db)):
    """Login user and return JWT token."""
    user = db.query(User).filter(User.email == payload.email).first()

    if not user:
        write_audit_log(
            db,
            request,
            action_type="login",
            result="failure",
            details={"reason": "invalid_credentials", "email": payload.email},
        )
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

    if not user.email_verified:
        if not settings.is_production and not EmailService.is_configured():
            user.email_verified = True
            if not db.query(UserSettings).filter(UserSettings.user_id == user.id).first():
                db.add(UserSettings(user_id=user.id))
            if not user.mfa_enabled and not user.mfa_pending_secret:
                user.mfa_pending_secret = MfaService.generate_secret()
            db.commit()
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Please verify your email before logging in"
            )

    now = datetime.now(timezone.utc)

    if clear_expired_lockout(user, now):
        db.commit()

    # Check if account is locked
    if is_account_locked(user, now):
        write_audit_log(
            db,
            request,
            action_type="login",
            result="failure",
            user_id=user.id,
            details={"reason": "account_locked"},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is temporarily locked. Try again later."
        )

    if not verify_password(payload.password, user.password_hash):
        if register_failed_login_attempt(user, now):
            try:
                EmailService.send_account_lockout_email(user.email, user.locked_until)
            except Exception:
                pass
        write_audit_log(
            db,
            request,
            action_type="login",
            result="failure",
            user_id=user.id,
            details={
                "reason": "invalid_credentials",
                "failed_login_attempts": user.failed_login_attempts,
                "locked_until": user.locked_until.isoformat() if user.locked_until else None,
            },
        )
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    reset_lockout_state(user)

    if not user.mfa_enabled or not user.mfa_secret:
        # All users (including admin) must complete MFA setup before accessing the system
        db.commit()
        return {
            "access_token": None,
            "token_type": "bearer",
            "user": None,
            "mfa_required": False,
            "mfa_token": None,
            "mfa_setup_required": True,
            "mfa_setup_token": create_mfa_setup_token(str(user.id)),
        }

    if user.mfa_enabled and user.mfa_secret:
        db.commit()
        return {
            "access_token": None,
            "token_type": "bearer",
            "user": None,
            "mfa_required": True,
            "mfa_token": create_mfa_login_token(str(user.id)),
            "mfa_setup_required": False,
            "mfa_setup_token": None,
        }

    # Generate token
    access_token, refresh_token = issue_session_tokens(db, request, user)
    user.last_login = datetime.now(timezone.utc)
    write_audit_log(
        db,
        request,
        action_type="login",
        result="success",
        user_id=user.id,
        details={"role": user.role.value, "mfa_required": False},
    )
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(user),
        "mfa_required": False,
        "mfa_token": None,
        "mfa_setup_required": False,
        "mfa_setup_token": None,
    }


@router.post("/auth/verify-email", response_model=RegistrationMfaSetupResponse)
def verify_email(request: EmailVerificationRequest, db: Session = Depends(get_db)):
    """Verify a newly registered email and start mandatory MFA setup."""
    user = None
    try:
        pending_registration = decode_registration_verification_token(request.token)
        existing_verified = db.query(User).filter(User.email == pending_registration["email"], User.email_verified == True).first()
        if existing_verified:
            user = existing_verified
        else:
            user = db.query(User).filter(User.email == pending_registration["email"]).first()
            if user:
                user.username = pending_registration["username"]
                user.password_hash = pending_registration["password_hash"]
                user.email_verified = True
            else:
                user = User(
                    username=pending_registration["username"],
                    email=pending_registration["email"],
                    password_hash=pending_registration["password_hash"],
                    email_verified=True,
                )
                db.add(user)
                db.flush()
                db.add(UserSettings(user_id=user.id))

    except HTTPException as exc:
        if exc.detail != "Invalid verification token":
            raise

        email = decode_email_verification_token(request.token)
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        user.email_verified = True


    if user.mfa_enabled and user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Microsoft Authenticator is already enabled for this account"
        )

    user.email_verified = True
    if not user.mfa_pending_secret:
        user.mfa_pending_secret = MfaService.generate_secret()
    setup_token = create_mfa_setup_token(str(user.id))
    db.commit()

    otp_uri = MfaService.build_otp_uri(user.email, user.mfa_pending_secret)
    return {
        "email": user.email,
        "setup_token": setup_token,
        "secret": user.mfa_pending_secret,
        "otp_auth_url": otp_uri,
        "qr_code_data_url": MfaService.build_qr_code_data_url(otp_uri),
        "message": "Email verified. Set up Microsoft Authenticator before first access.",
    }


@router.post("/auth/mfa/setup-registration", response_model=RegistrationMfaSetupResponse)
def setup_registration_mfa(request: RegistrationMfaSetupRequest, db: Session = Depends(get_db)):
    """Resume mandatory MFA setup for a verified account before first login."""
    user_id = decode_mfa_setup_token(request.setup_token)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verify your email before setting up MFA"
        )

    if user.mfa_enabled and user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled for this account"
        )

    if not user.mfa_pending_secret:
        user.mfa_pending_secret = MfaService.generate_secret()
    fresh_setup_token = create_mfa_setup_token(str(user.id))
    db.commit()

    otp_uri = MfaService.build_otp_uri(user.email, user.mfa_pending_secret)
    return {
        "email": user.email,
        "setup_token": fresh_setup_token,
        "secret": user.mfa_pending_secret,
        "otp_auth_url": otp_uri,
        "qr_code_data_url": MfaService.build_qr_code_data_url(otp_uri),
        "message": "Set up Microsoft Authenticator to complete your account access.",
    }


@router.post("/auth/mfa/complete-registration", response_model=TokenResponse)
def complete_registration_mfa(http_request: Request, request: RegistrationMfaCompleteRequest, db: Session = Depends(get_db)):
    """Finish mandatory MFA setup and grant first access."""
    user_id = decode_mfa_setup_token(request.setup_token)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verify your email before completing MFA setup"
        )

    if not user.mfa_pending_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start MFA setup first"
        )

    if not MfaService.verify_code(user.mfa_pending_secret, request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid authenticator code"
        )

    user.mfa_secret = user.mfa_pending_secret
    user.mfa_pending_secret = None
    user.mfa_enabled = True
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.now(timezone.utc)
    write_audit_log(
        db,
        http_request,
        action_type="MFA_setup",
        result="success",
        user_id=user.id,
        details={"flow": "registration"},
    )
    write_audit_log(
        db,
        http_request,
        action_type="login",
        result="success",
        user_id=user.id,
        details={"role": user.role.value, "mfa_required": True},
    )

    access_token, refresh_token = issue_session_tokens(db, http_request, user)
    db.commit()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(user),
        "mfa_required": False,
        "mfa_token": None,
        "mfa_setup_required": False,
        "mfa_setup_token": None,
    }


@router.post("/auth/forgot-password", response_model=ForgotPasswordChallengeResponse)
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Verify MFA and return a temporary password reset token to the app."""
    user = db.query(User).filter(User.email == request.email).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Multi-factor authentication is not enabled for this account"
        )

    if not MfaService.verify_code(user.mfa_secret, request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid authenticator code"
        )

    reset_token = create_password_reset_token(user.email)
    return {
        "message": "Authenticator verified. You can now set a new password.",
        "email": user.email,
        "reset_token": reset_token,
    }


@router.post("/auth/reset-password", response_model=MessageOnlyResponse)
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Reset a password using a recovery token."""
    token_email = decode_password_reset_token(request.token)
    if token_email.lower() != request.email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token does not match the provided email"
        )

    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user.password_hash = hash_password(request.new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    SessionService.revoke_user_sessions(db, user.id, reason="password_reset")
    db.commit()

    return {"message": "Password reset successfully"}


@router.post("/auth/mfa/login-verify", response_model=TokenResponse)
def verify_mfa_login(http_request: Request, request: MfaLoginRequest, db: Session = Depends(get_db)):
    """Complete login using an MFA code."""
    user_id = decode_mfa_login_token(request.mfa_token)
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled for this account"
        )

    if not MfaService.verify_code(user.mfa_secret, request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid authenticator code"
        )

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.now(timezone.utc)
    write_audit_log(
        db,
        http_request,
        action_type="login",
        result="success",
        user_id=user.id,
        details={"role": user.role.value, "mfa_required": True},
    )

    access_token, refresh_token = issue_session_tokens(db, http_request, user)
    db.commit()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(user),
        "mfa_required": False,
        "mfa_token": None,
        "mfa_setup_required": False,
        "mfa_setup_token": None,
    }


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh_access_token(
    http_request: Request,
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    """Refresh an authenticated session using a rotating refresh token."""
    session = SessionService.get_active_session_by_refresh_token(db, request.refresh_token)
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user or not user.is_active:
        SessionService.revoke_session(session, reason="user_inactive")
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive",
        )

    access_token, refresh_token = SessionService.rotate_refresh_token(db, session)
    write_audit_log(
        db,
        http_request,
        action_type="token_refresh",
        result="success",
        user_id=user.id,
        details={"session_id": str(session.id)},
    )
    db.commit()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(user),
        "mfa_required": False,
        "mfa_token": None,
        "mfa_setup_required": False,
        "mfa_setup_token": None,
    }


@router.post("/auth/logout", response_model=MessageOnlyResponse)
def logout(
    http_request: Request,
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    """Revoke a persistent session and its refresh token."""
    session = SessionService.get_active_session_by_refresh_token(db, request.refresh_token)
    SessionService.revoke_session(session, reason="logout")
    write_audit_log(
        db,
        http_request,
        action_type="logout",
        result="success",
        user_id=session.user_id,
        details={"session_id": str(session.id)},
    )
    db.commit()
    return {"message": "Logged out successfully"}


@router.get("/auth/mfa/setup", response_model=MfaSetupResponse)
def setup_mfa(
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a pending MFA secret and QR code for Microsoft Authenticator."""
    secret = MfaService.generate_secret()
    current_user.mfa_pending_secret = secret
    db.commit()

    otp_uri = MfaService.build_otp_uri(current_user.email, secret)
    return {
        "secret": secret,
        "otp_auth_url": otp_uri,
        "qr_code_data_url": MfaService.build_qr_code_data_url(otp_uri),
        "message": "Scan the QR code with Microsoft Authenticator and enter the current 6-digit code to enable MFA.",
    }


@router.post("/auth/mfa/enable", response_model=MessageOnlyResponse)
def enable_mfa(
    http_request: Request,
    request: MfaEnableRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Enable MFA after verifying the authenticator code."""
    if not current_user.mfa_pending_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start MFA setup first"
        )

    if not MfaService.verify_code(current_user.mfa_pending_secret, request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid authenticator code"
        )

    current_user.mfa_secret = current_user.mfa_pending_secret
    current_user.mfa_pending_secret = None
    current_user.mfa_enabled = True
    write_audit_log(
        db,
        http_request,
        action_type="MFA_setup",
        result="success",
        user_id=current_user.id,
        details={"flow": "self_service"},
    )
    db.commit()

    return {"message": "Multi-factor authentication enabled successfully"}


@router.post("/auth/mfa/disable", response_model=MessageOnlyResponse)
def disable_mfa(
    http_request: Request,
    request: MfaEnableRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Disable MFA after confirming a valid authenticator code."""
    if not current_user.mfa_enabled or not current_user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled"
        )

    if not MfaService.verify_code(current_user.mfa_secret, request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid authenticator code"
        )

    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    current_user.mfa_pending_secret = None
    write_audit_log(
        db,
        http_request,
        action_type="MFA_disable",
        result="success",
        user_id=current_user.id,
        details=None,
    )
    db.commit()

    return {"message": "Multi-factor authentication disabled"}


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
    """List all charging stations with optional risk-score filters and dynamic color visualization."""
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
    
    # Convert to dict and enrich with colors for map visualization
    stations_dict = [
        {
            "id": str(s.id),
            "name": s.name,
            "latitude": s.latitude,
            "longitude": s.longitude,
            "city": s.city,
            "address": s.address,
            "status": s.status,
            "risk_score": s.risk_score,
            "cyber_risk_level": s.cyber_risk_level,
            "firmware_version": s.firmware_version,
            "firmware_age_days": s.firmware_age_days,
            "temperature_celsius": s.temperature_celsius,
            "power_status": s.power_status,
            "fault_count": s.fault_count,
            "last_scored_at": s.last_scored_at,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }
        for s in stations
    ]
    
    # Enrich with dynamic colors based on risk scores
    enriched = RiskScoreMLService.enrich_stations_with_colors(stations_dict)
    return enriched


@router.get("/stations/{station_id}", response_model=ChargingStationDetailResponse)
def get_station(station_id: UUID, db: Session = Depends(get_db)):
    """Get a specific charging station with dynamic color visualization."""
    station = db.query(ChargingStation).filter(ChargingStation.id == station_id).first()
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Station not found"
        )
    
    # Convert to dict and enrich with color
    station_dict = {
        "id": str(station.id),
        "name": station.name,
        "latitude": station.latitude,
        "longitude": station.longitude,
        "city": station.city,
        "address": station.address,
        "operator": station.operator,
        "connector_types": station.connector_types,
        "charging_power_kw": station.charging_power_kw,
        "status": station.status,
        "risk_score": station.risk_score,
        "cyber_risk_level": station.cyber_risk_level,
        "firmware_version": station.firmware_version,
        "firmware_age_days": station.firmware_age_days,
        "temperature_celsius": station.temperature_celsius,
        "power_status": station.power_status,
        "fault_count": station.fault_count,
        "last_scored_at": station.last_scored_at,
        "created_at": station.created_at,
        "updated_at": station.updated_at,
    }
    
    # Enrich with dynamic color based on risk score
    enriched = RiskScoreMLService.enrich_station_with_color(station_dict)
    return enriched
@router.get("/stations/{station_id}/cyber-score", response_model=StationCyberScoreResponse)
def get_station_cyber_score(
    station_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    station = db.query(ChargingStation).filter(ChargingStation.id == station_id).first()
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Station not found"
        )

    score_rows = (
        db.query(CyberScore, CyberCriterion)
        .join(CyberCriterion, CyberScore.criterion_id == CyberCriterion.id)
        .filter(CyberScore.station_id == station_id)
        .order_by(CyberCriterion.criterion_name.asc())
        .all()
    )

    if not score_rows:
        return {
            "station_id": station.id,
            "station_name": station.name,
            "overall_score": 0.0,
            "overall_risk_level": "LOW",
            "criteria_count": 0,
            "breakdown": []
        }

    total_weight = sum(criterion.weight for _, criterion in score_rows)
    weighted_sum = sum(score.score_value * criterion.weight for score, criterion in score_rows)

    overall_score = 0.0
    if total_weight > 0:
        overall_score = round((weighted_sum / total_weight) * 25, 1)

    overall_risk_level = get_overall_cyber_risk_level(overall_score)

    breakdown = [
        {
            "criterion_id": criterion.id,
            "criterion_name": criterion.criterion_name,
            "description": criterion.description,
            "iec_reference": criterion.iec_reference,
            "weight": criterion.weight,
            "score_value": score.score_value,
            "risk_rating": score.risk_rating,
            "evaluated_at": score.evaluated_at,
            "notes": score.notes,
        }
        for score, criterion in score_rows
    ]

    return {
        "station_id": station.id,
        "station_name": station.name,
        "overall_score": overall_score,
        "overall_risk_level": overall_risk_level,
        "criteria_count": len(breakdown),
        "breakdown": breakdown
    }




@router.get("/stations/{station_id}/incidents", response_model=List[ReportDetailResponse])
def get_station_incidents(
    station_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(50, le=100)
):
    """Get incident history for a specific charging station."""
    station = db.query(ChargingStation).filter(ChargingStation.id == station_id).first()
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Station not found"
        )
    incidents = (
        db.query(Report)
        .filter(Report.station_id == station_id)
        .order_by(Report.created_at.desc())
        .limit(limit)
        .all()
    )
    return incidents


@router.post("/stations", response_model=ChargingStationDetailResponse)
def create_station(
    http_request: Request,
    request: ChargingStationCreateUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Create a new charging station (admin only)."""
    payload = request.model_dump()
    if "risk_score" in payload:
        payload["safety_score"] = payload.pop("risk_score")
    station = ChargingStation(**payload)
    db.add(station)
    write_audit_log(
        db,
        http_request,
        action_type="admin_create_station",
        result="success",
        user_id=current_user.id,
        details={"station_name": request.name},
    )
    db.commit()
    db.refresh(station)
    return station


@router.put("/stations/{station_id}", response_model=ChargingStationDetailResponse)
def update_station(
    http_request: Request,
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
    
    payload = request.model_dump(exclude_unset=True)
    if "risk_score" in payload:
        payload["safety_score"] = payload.pop("risk_score")
    previous_risk_score = station.safety_score if "safety_score" in payload else None

    for key, value in payload.items():
        setattr(station, key, value)
    
    station.updated_at = datetime.utcnow()
    if "safety_score" in payload:
        notify_on_risk_state_change(
            db,
            station_id=station.id,
            old_score=previous_risk_score,
            new_score=station.safety_score,
            timestamp=station.updated_at,
        )
    write_audit_log(
        db,
        http_request,
        action_type="admin_update_station",
        result="success",
        user_id=current_user.id,
        details={"station_id": str(station_id), "updated_fields": sorted(payload.keys())},
    )
    db.commit()
    db.refresh(station)
    return station


# ============== Incidents ==============
@router.post("/reports", response_model=ReportResponse, status_code=201)
@router.post("/incidents", response_model=ReportResponse, status_code=201)
def create_report(
    request: ReportCreate,
    background_tasks: BackgroundTasks,
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
        description=request.description,
        status=ReportStatus.resolved,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # Recalculate the hybrid ML risk score before returning so the frontend can
    # refresh the station in real time without a reload.
    from app.services.feedback_processor import FeedbackProcessor
    FeedbackProcessor.process_feedback(
        report_id=str(report.id),
        station_id=str(station.id),
        db=db,
    )

    return report


@router.post("/internal/process-new-feedback")
def process_new_feedback(
    http_request: Request,
    request: InternalFeedbackProcessRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Internal webhook for triggering ML updates."""
    from app.services.feedback_processor import FeedbackProcessor
    result = FeedbackProcessor.process_feedback(
        report_id=str(request.report_id),
        station_id=str(request.station_id),
        db=db,
    )
    write_audit_log(
        db,
        http_request,
        action_type="admin_process_feedback",
        result="success",
        user_id=current_user.id,
        details={"report_id": str(request.report_id), "station_id": str(request.station_id)},
    )
    db.commit()
    return {"status": "Processed", "result": result}

@router.get("/reports", response_model=List[ReportDetailResponse])
@router.get("/incidents", response_model=List[ReportDetailResponse])
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
@router.get("/incidents/{report_id}", response_model=ReportDetailResponse)
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
    http_request: Request,
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
    write_audit_log(
        db,
        http_request,
        action_type="admin_update_report",
        result="success",
        user_id=current_user.id,
        details={"report_id": str(report_id), "status": request.status.value},
    )
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
    http_request: Request,
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
    auth_header = http_request.headers.get("authorization", "")
    current_session_id = None
    if auth_header.lower().startswith("bearer "):
        current_session_id = decode_token(auth_header.split(" ", 1)[1].strip()).get("session_id")

    revoked_sessions = SessionService.revoke_user_sessions(
        db,
        current_user.id,
        reason="password_change",
        except_session_id=current_session_id,
    )
    write_audit_log(
        db,
        http_request,
        action_type="password_change",
        result="success",
        user_id=current_user.id,
        details={"revoked_sessions": revoked_sessions},
    )
    db.commit()

    return {"message": "Password changed successfully"}


@router.post("/me/delete", response_model=MessageOnlyResponse)
def delete_account(
    http_request: Request,
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
    SessionService.revoke_user_sessions(db, current_user.id, reason="account_deleted")
    write_audit_log(
        db,
        http_request,
        action_type="account_deletion",
        result="success",
        user_id=current_user.id,
        details={"email": current_user.email},
    )
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
    http_request: Request,
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
    write_audit_log(
        db,
        http_request,
        action_type="admin_deactivate_user",
        result="success",
        user_id=current_user.id,
        details={"target_user_id": str(user_id), "target_email": user.email},
    )
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
