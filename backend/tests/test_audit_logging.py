import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from app.api.routes import write_audit_log


class AuditLoggingTests(unittest.TestCase):
    def test_write_audit_log_uses_audit_service(self):
        request = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"user-agent": "pytest"},
        )

        with patch("app.api.routes.AuditService.log_event_safely") as log_event_safely:
            write_audit_log(
                Mock(),
                request,
                action_type="login",
                result="success",
                user_id=uuid4(),
                details={"source": "test"},
            )

        log_event_safely.assert_called_once()
        _, kwargs = log_event_safely.call_args
        self.assertEqual(kwargs["action_type"], "login")
        self.assertEqual(kwargs["result"], "success")
        self.assertEqual(kwargs["ip_address"], "127.0.0.1")
        self.assertEqual(kwargs["user_agent"], "pytest")


if __name__ == "__main__":
    unittest.main()
