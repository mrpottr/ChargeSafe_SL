from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Notification, ReportStatus, UserRole
from tests.factories import DEFAULT_PASSWORD


def test_report_creation_updates_station_score_history_and_notifications(
    client,
    user_factory,
    station_factory,
    auth_headers_factory,
    db_session: Session,
):
    reporter = user_factory(password=DEFAULT_PASSWORD)
    observer = user_factory(password=DEFAULT_PASSWORD)
    station = station_factory(risk_score=24.0)
    headers, _refresh_token = auth_headers_factory(reporter)

    create_report_response = client.post(
        "/api/reports",
        headers=headers,
        json={
            "station_id": str(station.id),
            "report_type": "Overheating",
            "severity": 5,
            "description": "The charger became very hot during the session.",
        },
    )
    assert create_report_response.status_code == 201
    report_payload = create_report_response.json()
    assert report_payload["status"] == "RESOLVED"

    db_session.refresh(station)
    assert station.safety_score == 54.0
    assert station.last_scored_at is not None

    station_notifications = (
        db_session.query(Notification)
        .filter(Notification.title.ilike(f"%{station.name}%"))
        .all()
    )
    assert len(station_notifications) == 2

    list_reports_response = client.get("/api/reports", headers=headers)
    assert list_reports_response.status_code == 200
    assert len(list_reports_response.json()) == 1

    incidents_response = client.get(f"/api/stations/{station.id}/incidents", headers=headers)
    assert incidents_response.status_code == 200
    incidents_payload = incidents_response.json()
    assert len(incidents_payload) == 1
    assert incidents_payload[0]["id"] == report_payload["id"]


def test_admin_can_create_update_station_and_review_reports(
    client,
    user_factory,
    station_factory,
    report_factory,
    auth_headers_factory,
    db_session: Session,
):
    admin = user_factory(role=UserRole.admin, password=DEFAULT_PASSWORD)
    standard_user = user_factory(password=DEFAULT_PASSWORD)
    existing_station = station_factory(risk_score=26.0)
    report = report_factory(user_id=standard_user.id, station_id=existing_station.id)
    headers, _refresh_token = auth_headers_factory(admin)

    create_station_response = client.post(
        "/api/stations",
        headers=headers,
        json={
            "name": "Admin Created Station",
            "latitude": 7.0,
            "longitude": 80.0,
            "city": "Kandy",
            "address": "Kandy address",
            "status": "operational",
            "risk_score": 45,
            "fault_count": 1,
        },
    )
    assert create_station_response.status_code == 200
    created_station_payload = create_station_response.json()
    assert created_station_payload["name"] == "Admin Created Station"
    assert created_station_payload["risk_score"] == 45.0

    update_station_response = client.put(
        f"/api/stations/{existing_station.id}",
        headers=headers,
        json={
            "name": existing_station.name,
            "latitude": existing_station.latitude,
            "longitude": existing_station.longitude,
            "city": existing_station.city,
            "address": existing_station.address,
            "status": existing_station.status.value,
            "risk_score": 82,
            "fault_count": 4,
        },
    )
    assert update_station_response.status_code == 200
    assert update_station_response.json()["risk_score"] == 82.0

    admin_reports_response = client.get("/api/admin/reports", headers=headers)
    assert admin_reports_response.status_code == 200
    assert len(admin_reports_response.json()) == 1

    update_report_response = client.put(
        f"/api/reports/{report.id}",
        headers=headers,
        json={"status": "FLAGGED"},
    )
    assert update_report_response.status_code == 200
    assert update_report_response.json()["status"] == "FLAGGED"

    db_session.refresh(report)
    assert report.status == ReportStatus.flagged

    admin_users_response = client.get("/api/admin/users", headers=headers)
    assert admin_users_response.status_code == 200
    assert {item["email"] for item in admin_users_response.json()} == {
        admin.email,
        standard_user.email,
    }


def test_non_admin_is_forbidden_from_admin_endpoints(client, seeded_standard_user, auth_headers_factory):
    headers, _refresh_token = auth_headers_factory(seeded_standard_user)

    users_response = client.get("/api/admin/users", headers=headers)
    assert users_response.status_code == 403

    create_station_response = client.post(
        "/api/stations",
        headers=headers,
        json={
            "name": "Forbidden Station",
            "latitude": 7.1,
            "longitude": 80.1,
        },
    )
    assert create_station_response.status_code == 403
