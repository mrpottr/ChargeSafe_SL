import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from app.core.account_lockout import (
    ACCOUNT_LOCKOUT_DURATION,
    clear_expired_lockout,
    is_account_locked,
    register_failed_login_attempt,
    reset_lockout_state,
)


def build_user(**overrides):
    base = {
        "failed_login_attempts": 0,
        "locked_until": None,
        "email": "user@example.com",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class AccountLockoutTests(unittest.TestCase):
    def test_fifth_failed_attempt_locks_for_thirty_minutes_and_triggers_notification(self):
        now = datetime.now(timezone.utc)
        user = build_user(failed_login_attempts=4)
        notify = Mock()

        locked_now = register_failed_login_attempt(user, now)
        if locked_now:
            notify(user.email, user.locked_until)

        self.assertTrue(locked_now)
        self.assertEqual(user.failed_login_attempts, 5)
        self.assertEqual(user.locked_until, now + ACCOUNT_LOCKOUT_DURATION)
        notify.assert_called_once_with(user.email, user.locked_until)

    def test_active_lockout_blocks_access(self):
        now = datetime.now(timezone.utc)
        user = build_user(locked_until=now + timedelta(minutes=10))

        self.assertTrue(is_account_locked(user, now))

    def test_expired_lockout_auto_unlocks(self):
        now = datetime.now(timezone.utc)
        user = build_user(
            failed_login_attempts=5,
            locked_until=now - timedelta(seconds=1),
        )

        cleared = clear_expired_lockout(user, now)

        self.assertTrue(cleared)
        self.assertEqual(user.failed_login_attempts, 0)
        self.assertIsNone(user.locked_until)

    def test_reset_lockout_state_clears_attempts_and_lock(self):
        user = build_user(
            failed_login_attempts=3,
            locked_until=datetime.now(timezone.utc) + timedelta(minutes=5),
        )

        reset_lockout_state(user)

        self.assertEqual(user.failed_login_attempts, 0)
        self.assertIsNone(user.locked_until)


if __name__ == "__main__":
    unittest.main()
