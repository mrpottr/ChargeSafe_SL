import unittest
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4
import sys
import types
import importlib.metadata as importlib_metadata


if "email_validator" not in sys.modules:
    sys.modules["email_validator"] = types.SimpleNamespace(
        EmailNotValidError=ValueError,
        validate_email=lambda email, *args, **kwargs: types.SimpleNamespace(normalized=email),
    )

_original_version = importlib_metadata.version


def _patched_version(package_name: str) -> str:
    if package_name == "email-validator":
        return "2.0.0"
    return _original_version(package_name)


importlib_metadata.version = _patched_version

from app.models import IncidentType, Notification
from app.schemas import ReportCreate
from app.services.risk_state_observer import (
    build_score_update_message,
    build_state_change_message,
    map_risk_category,
    notify_on_risk_state_change,
)


class FakeQuery:
    def __init__(self, model, session):
        self.model = model
        self.session = session

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        if self.model.__name__ == "ChargingStation":
            return self.session.station
        if self.model.__name__ == "Notification":
            return None
        return None

    def all(self):
        if self.model.__name__ == "User":
            return self.session.users
        return []


class FakeSession:
    def __init__(self, station, users):
        self.station = station
        self.users = users
        self.added = []

    def query(self, model):
        return FakeQuery(model, self)

    def add(self, value):
        self.added.append(value)


class FeedbackAndRiskNotificationTests(unittest.TestCase):
    def test_positive_feedback_accepts_missing_severity(self):
        payload = ReportCreate(
            station_id=uuid4(),
            report_type="Positive",
            severity=None,
            description="Charging session completed smoothly with no issues at all.",
        )

        self.assertEqual(payload.report_type, IncidentType.positive)
        self.assertIsNone(payload.severity)

    def test_frontend_category_aliases_are_normalized(self):
        payload = ReportCreate(
            station_id=uuid4(),
            report_type="Connectivity / Offline",
            severity=4,
            description="The station stayed offline for the whole charging attempt.",
        )

        self.assertEqual(payload.report_type, IncidentType.network_outage)

    def test_non_positive_feedback_still_requires_severity(self):
        with self.assertRaises(Exception):
            ReportCreate(
                station_id=uuid4(),
                report_type="Overheating",
                severity=None,
                description="The charger became extremely hot during the session.",
            )

    def test_risk_category_mapping_and_message(self):
        self.assertIsNone(map_risk_category(None))
        self.assertEqual(map_risk_category(25.0), "LOW")
        self.assertEqual(map_risk_category(55.0), "MEDIUM")
        self.assertEqual(map_risk_category(91.0), "HIGH")
        self.assertEqual(
            build_state_change_message("Station A", "LOW", "HIGH"),
            "Charging Station Station A has changed from LOW to HIGH.",
        )
        self.assertEqual(
            build_score_update_message("Station A", 44.0, 49.5, "MEDIUM"),
            "Charging Station Station A risk score changed from 44.0 to 49.5 and is currently MEDIUM.",
        )

    def test_notification_created_only_when_band_changes(self):
        station = SimpleNamespace(id=uuid4(), name="Colombo Central")
        users = [
            SimpleNamespace(id=uuid4(), is_active=True, settings=SimpleNamespace(push_notifications_enabled=True)),
            SimpleNamespace(id=uuid4(), is_active=True, settings=SimpleNamespace(push_notifications_enabled=False)),
            SimpleNamespace(id=uuid4(), is_active=True, settings=None),
        ]
        session = FakeSession(station=station, users=users)
        timestamp = datetime(2026, 5, 8, 12, 0, 0)

        created = notify_on_risk_state_change(
            session,
            station_id=station.id,
            old_score=22.0,
            new_score=81.0,
            timestamp=timestamp,
        )

        self.assertEqual(created, 2)
        self.assertEqual(len(session.added), 2)
        self.assertTrue(all(isinstance(item, Notification) for item in session.added))
        self.assertTrue(all(item.created_at == timestamp for item in session.added))
        self.assertTrue(all(item.notification_type == "danger" for item in session.added))
        self.assertEqual(
            session.added[0].message,
            "Charging Station Colombo Central has changed from LOW to HIGH.",
        )

    def test_no_notification_for_initial_or_same_band_updates(self):
        station = SimpleNamespace(id=uuid4(), name="Kandy Station")
        users = [SimpleNamespace(id=uuid4(), is_active=True, settings=None)]
        session = FakeSession(station=station, users=users)
        timestamp = datetime(2026, 5, 8, 12, 30, 0)

        created_initial = notify_on_risk_state_change(
            session,
            station_id=station.id,
            old_score=None,
            new_score=25.0,
            timestamp=timestamp,
        )
        created_same_score = notify_on_risk_state_change(
            session,
            station_id=station.id,
            old_score=10.0,
            new_score=10.0,
            timestamp=timestamp,
        )

        self.assertEqual(created_initial, 0)
        self.assertEqual(created_same_score, 0)
        self.assertEqual(session.added, [])

    def test_same_band_score_change_still_creates_notification(self):
        station = SimpleNamespace(id=uuid4(), name="Galle Station")
        users = [SimpleNamespace(id=uuid4(), is_active=True, settings=None)]
        session = FakeSession(station=station, users=users)
        timestamp = datetime(2026, 5, 8, 13, 0, 0)

        created = notify_on_risk_state_change(
            session,
            station_id=station.id,
            old_score=45.0,
            new_score=52.5,
            timestamp=timestamp,
        )

        self.assertEqual(created, 1)
        self.assertEqual(len(session.added), 1)
        self.assertEqual(session.added[0].title, "Risk Score Updated - Galle Station")
        self.assertEqual(
            session.added[0].message,
            "Charging Station Galle Station risk score changed from 45.0 to 52.5 and is currently MEDIUM.",
        )
        self.assertEqual(session.added[0].notification_type, "warn")


if __name__ == "__main__":
    unittest.main()
