from __future__ import annotations

from app.models import UserRole
from tests.factories import DEFAULT_PASSWORD, current_totp


def test_register_to_logout_end_to_end(client):
    register_response = client.post(
        "/api/auth/register",
        json={
            "username": "journey_user",
            "email": "journey_user@example.com",
            "password": "StrongPass1",
        },
    )
    assert register_response.status_code == 200
    register_payload = register_response.json()
    assert register_payload["next_step"] == "mfa_setup"
    assert register_payload["setup_token"]

    setup_response = client.post(
        "/api/auth/mfa/setup-registration",
        json={"setup_token": register_payload["setup_token"]},
    )
    assert setup_response.status_code == 200
    setup_payload = setup_response.json()
    assert setup_payload["email"] == "journey_user@example.com"
    assert setup_payload["secret"]

    complete_response = client.post(
        "/api/auth/mfa/complete-registration",
        json={
            "setup_token": setup_payload["setup_token"],
            "code": current_totp(setup_payload["secret"]),
        },
    )
    assert complete_response.status_code == 200
    complete_payload = complete_response.json()
    assert complete_payload["access_token"]
    assert complete_payload["refresh_token"]
    assert complete_payload["user"]["mfa_enabled"] is True

    protected_response = client.get(
        "/api/me",
        headers={"Authorization": f"Bearer {complete_payload['access_token']}"},
    )
    assert protected_response.status_code == 200
    assert protected_response.json()["email"] == "journey_user@example.com"

    logout_response = client.post(
        "/api/auth/logout",
        json={"refresh_token": complete_payload["refresh_token"]},
    )
    assert logout_response.status_code == 200

    revoked_session_response = client.get(
        "/api/me",
        headers={"Authorization": f"Bearer {complete_payload['access_token']}"},
    )
    assert revoked_session_response.status_code == 401


def test_user_station_incident_and_settings_journey(
    client,
    user_factory,
    station_factory,
    login_with_mfa,
):
    station = station_factory(risk_score=28.0)
    user = user_factory(password=DEFAULT_PASSWORD)
    login_payload = login_with_mfa(user, DEFAULT_PASSWORD)
    headers = {"Authorization": f"Bearer {login_payload['access_token']}"}

    stations_response = client.get("/api/stations")
    assert stations_response.status_code == 200
    assert any(item["id"] == str(station.id) for item in stations_response.json())

    submit_incident_response = client.post(
        "/api/incidents",
        headers=headers,
        json={
            "station_id": str(station.id),
            "report_type": "Network Outage",
            "severity": 4,
            "description": "The station stayed offline for most of the charging attempt.",
        },
    )
    assert submit_incident_response.status_code == 201
    created_incident = submit_incident_response.json()

    reports_response = client.get("/api/reports", headers=headers)
    assert reports_response.status_code == 200
    assert reports_response.json()[0]["id"] == created_incident["id"]

    update_profile_response = client.put("/api/me", headers=headers, params={"username": "journey_updated"})
    assert update_profile_response.status_code == 200
    assert update_profile_response.json()["username"] == "journey_updated"

    update_settings_response = client.put(
        "/api/settings",
        headers=headers,
        json={"alert_threshold": 90, "language": "Tamil"},
    )
    assert update_settings_response.status_code == 200
    assert update_settings_response.json()["language"] == "Tamil"


def test_admin_only_end_to_end_journey(client, user_factory, station_factory, login_with_mfa):
    admin = user_factory(role=UserRole.admin, password=DEFAULT_PASSWORD)
    regular_user = user_factory(password=DEFAULT_PASSWORD)
    station = station_factory()

    login_payload = login_with_mfa(admin, DEFAULT_PASSWORD)
    headers = {"Authorization": f"Bearer {login_payload['access_token']}"}

    admin_users_response = client.get("/api/admin/users", headers=headers)
    assert admin_users_response.status_code == 200
    assert {item["email"] for item in admin_users_response.json()} == {
        admin.email,
        regular_user.email,
    }

    admin_stations_response = client.get("/api/admin/stations", headers=headers)
    assert admin_stations_response.status_code == 200
    assert admin_stations_response.json()[0]["id"] == str(station.id)
