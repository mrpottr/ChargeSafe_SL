from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_refresh_token
from app.models import User, UserSession


# This function calculates and returns the current time in Coordinated Universal Time (UTC). 
# It is built using the built-in datetime module and ensures all time-based operations 
# across the service remain standardized and timezone-aware.
def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionService:
    # This function creates a secure cryptographic hash of a given refresh token. 
    # It is built using the SHA-256 algorithm from Python's hashlib library, allowing the system 
    # to securely store tokens in the database without exposing their raw values.
    @staticmethod
    def hash_refresh_token(refresh_token: str) -> str:
        return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()

    # This function calculates the expiration timestamp for a newly issued refresh token. 
    # It is built by taking the current UTC time and adding a configurable number of days 
    # defined in the application's core settings.
    @staticmethod
    def _refresh_expiry() -> datetime:
        return _utc_now() + timedelta(days=settings.refresh_token_expire_days)

    # This function determines the time threshold used to detect inactive user sessions. 
    # It is built by subtracting the configured idle timeout duration from the current UTC time, 
    # returning a strict cutoff point for session validity.
    @staticmethod
    def _idle_cutoff() -> datetime:
        return _utc_now() - timedelta(minutes=settings.session_idle_timeout_minutes)

    # This function initializes and registers a new active session for a specific user upon login. 
    # It is built by generating unique tokens and securely storing the session's metadata, 
    # such as IP address and browser agent, within the database.
    @staticmethod
    def create_session(
        db: Session,
        user: User,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[str, str, UserSession]:
        session_id = uuid.uuid4()
        refresh_token = create_refresh_token(str(user.id), session_id)
        session = UserSession(
            id=session_id,
            user_id=user.id,
            refresh_token_hash=SessionService.hash_refresh_token(refresh_token),
            expires_at=SessionService._refresh_expiry(),
            last_seen_at=_utc_now(),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(session)
        db.flush()
        access_token = create_access_token(str(user.id), session_id=session_id)
        return access_token, refresh_token, session

    # This function retrieves and validates an existing user session based on its refresh token. 
    # It is built to decode the token, query the database for the matching session, 
    # and strictly verify that the provided token hash matches the stored record.
    @staticmethod
    def get_active_session_by_refresh_token(db: Session, refresh_token: str) -> UserSession:
        payload = decode_refresh_token(refresh_token)
        session_id = payload["session_id"]
        session = db.query(UserSession).filter(UserSession.id == session_id).first()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh session not found",
            )

        expected_hash = SessionService.hash_refresh_token(refresh_token)
        if session.refresh_token_hash != expected_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token does not match the current session",
            )

        SessionService.ensure_session_is_active(session)
        return session

    # This function performs a rigorous health check on a given user session to confirm it is still valid. 
    # It is built using conditional checks against expiration dates, revocation statuses, 
    # and the system's idle timeout constraints to protect against unauthorized access.
    @staticmethod
    def ensure_session_is_active(session: UserSession) -> None:
        now = _utc_now()
        if session.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked",
            )
        if session.expires_at.replace(tzinfo=timezone.utc) <= now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has expired",
            )
        if session.last_seen_at.replace(tzinfo=timezone.utc) < SessionService._idle_cutoff():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired due to inactivity",
            )

    # This function updates the 'last seen' timestamp of a user's session to prevent it from idling out. 
    # It is built with a throttling mechanism that only modifies the session if it hasn't 
    # been updated within the last minute, minimizing unnecessary database writes.
    @staticmethod
    def touch_session(session: UserSession) -> None:
        now = _utc_now()
        previous = session.last_seen_at
        if previous is None or previous.replace(tzinfo=timezone.utc) < now - timedelta(minutes=1):
            session.last_seen_at = now

    # This function issues a fresh pair of access and refresh tokens while invalidating the old ones. 
    # It is built by generating new tokens, updating the session's hash and expiry time 
    # in the database, and returning the updated credentials.
    @staticmethod
    def rotate_refresh_token(db: Session, session: UserSession) -> tuple[str, str]:
        refresh_token = create_refresh_token(str(session.user_id), str(session.id))
        session.refresh_token_hash = SessionService.hash_refresh_token(refresh_token)
        session.expires_at = SessionService._refresh_expiry()
        session.last_seen_at = _utc_now()
        db.flush()
        access_token = create_access_token(str(session.user_id), session_id=str(session.id))
        return access_token, refresh_token

    # This function permanently disables a specific user session, typically during logout or due to a security event. 
    # It is built by marking the session with a revocation timestamp and an explicit reason 
    # so that any subsequent attempts to use the session are denied.
    @staticmethod
    def revoke_session(session: UserSession, *, reason: str) -> None:
        if session.revoked_at is None:
            session.revoked_at = _utc_now()
            session.revoke_reason = reason

    # This function terminates all active sessions associated with a specific user account. 
    # It is built by querying the database for all valid sessions of the user and systematically 
    # revoking each one, optionally leaving a single specified session active.
    @staticmethod
    def revoke_user_sessions(
        db: Session,
        user_id,
        *,
        reason: str,
        except_session_id=None,
    ) -> int:
        query = db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
        if except_session_id is not None:
            query = query.filter(UserSession.id != except_session_id)

        sessions = query.all()
        for session in sessions:
            SessionService.revoke_session(session, reason=reason)
        db.flush()
        return len(sessions)
