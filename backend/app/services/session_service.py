from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_refresh_token
from app.models import User, UserSession


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionService:
    @staticmethod
    def hash_refresh_token(refresh_token: str) -> str:
        return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()

    @staticmethod
    def _refresh_expiry() -> datetime:
        return _utc_now() + timedelta(days=settings.refresh_token_expire_days)

    @staticmethod
    def _idle_cutoff() -> datetime:
        return _utc_now() - timedelta(minutes=settings.session_idle_timeout_minutes)

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

    @staticmethod
    def touch_session(session: UserSession) -> None:
        now = _utc_now()
        previous = session.last_seen_at
        if previous is None or previous.replace(tzinfo=timezone.utc) < now - timedelta(minutes=1):
            session.last_seen_at = now

    @staticmethod
    def rotate_refresh_token(db: Session, session: UserSession) -> tuple[str, str]:
        refresh_token = create_refresh_token(str(session.user_id), str(session.id))
        session.refresh_token_hash = SessionService.hash_refresh_token(refresh_token)
        session.expires_at = SessionService._refresh_expiry()
        session.last_seen_at = _utc_now()
        db.flush()
        access_token = create_access_token(str(session.user_id), session_id=str(session.id))
        return access_token, refresh_token

    @staticmethod
    def revoke_session(session: UserSession, *, reason: str) -> None:
        if session.revoked_at is None:
            session.revoked_at = _utc_now()
            session.revoke_reason = reason

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
