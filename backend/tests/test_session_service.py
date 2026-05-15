import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from fastapi import HTTPException

from app.core.security import decode_refresh_token, decode_token
from app.services.session_service import SessionService


class SessionServiceTests(unittest.TestCase):
    def test_create_session_returns_bound_access_and_refresh_tokens(self):
        db = Mock()
        user = SimpleNamespace(id=uuid4())

        access_token, refresh_token, session = SessionService.create_session(db, user)

        decoded_access = decode_token(access_token)
        decoded_refresh = decode_refresh_token(refresh_token)

        self.assertEqual(decoded_access["user_id"], str(user.id))
        self.assertEqual(decoded_access["session_id"], str(session.id))
        self.assertEqual(decoded_refresh["user_id"], str(user.id))
        self.assertEqual(decoded_refresh["session_id"], str(session.id))
        self.assertEqual(session.refresh_token_hash, SessionService.hash_refresh_token(refresh_token))
        db.add.assert_called_once()
        db.flush.assert_called()

    def test_ensure_session_is_active_rejects_revoked_session(self):
        session = SimpleNamespace(
            revoked_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            last_seen_at=datetime.now(timezone.utc),
        )

        with self.assertRaises(HTTPException) as context:
            SessionService.ensure_session_is_active(session)

        self.assertEqual(context.exception.status_code, 401)

    def test_ensure_session_is_active_rejects_idle_session(self):
        session = SimpleNamespace(
            revoked_at=None,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            last_seen_at=datetime.now(timezone.utc) - timedelta(minutes=25),
        )

        with self.assertRaises(HTTPException) as context:
            SessionService.ensure_session_is_active(session)

        self.assertEqual(context.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
