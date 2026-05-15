import re
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.db.session import get_db
from app.main import app
from app.schemas import InternalFeedbackProcessRequest, MfaEnableRequest, MfaLoginRequest


class DummySession:
    pass


def override_get_db():
    yield DummySession()


class InputValidationSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_startup = list(app.router.on_startup)
        cls.original_shutdown = list(app.router.on_shutdown)
        app.router.on_startup.clear()
        app.router.on_shutdown.clear()
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_db, None)
        app.router.on_startup[:] = cls.original_startup
        app.router.on_shutdown[:] = cls.original_shutdown
        cls.client.close()

    def test_mfa_codes_must_be_six_digits(self):
        with self.assertRaises(ValidationError):
            MfaEnableRequest(code="12'345")

        with self.assertRaises(ValidationError):
            MfaLoginRequest(mfa_token="a" * 16, code="ABC123")

    def test_internal_feedback_request_rejects_non_uuid_injection_payloads(self):
        with self.assertRaises(ValidationError):
            InternalFeedbackProcessRequest(
                report_id="' OR 1=1 --",
                station_id="550e8400-e29b-41d4-a716-446655440000",
            )

    def test_login_rejects_sql_injection_email_payload(self):
        response = self.client.post(
            "/api/auth/login",
            json={"email": "' OR 1=1 --", "password": "wrongpass"},
        )
        self.assertEqual(response.status_code, 422)

    def test_internal_feedback_rejects_sql_injection_payload(self):
        response = self.client.post(
            "/api/internal/process-new-feedback",
            json={"report_id": "' OR 1=1 --", "station_id": "' OR 1=1 --"},
        )
        self.assertEqual(response.status_code, 401)

    def test_routes_do_not_use_string_interpolated_sql(self):
        routes_source = Path(__file__).resolve().parents[1] / "app" / "api" / "routes.py"
        source_text = routes_source.read_text(encoding="utf-8")

        forbidden_patterns = [
            r'text\s*\(\s*f["\']',
            r'execute\s*\(\s*f["\']',
            r'execute\s*\(\s*".*\{.*\}.*"',
            r'execute\s*\(\s*\'.*\{.*\}.*\'',
        ]

        for pattern in forbidden_patterns:
            self.assertIsNone(
                re.search(pattern, source_text),
                f"Unsafe SQL interpolation pattern found: {pattern}",
            )


if __name__ == "__main__":
    unittest.main()
