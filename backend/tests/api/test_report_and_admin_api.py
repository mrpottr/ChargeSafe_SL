from __future__ import annotations

from app.models import ReportStatus, UserRole
from tests.factories import DEFAULT_PASSWORD


def test_reports_validate_payloads_and_handle_missing_station(
    client,
    seeded_standard_user,
    seeded_station,
    auth_headers_factory,
):
    headers, _refresh_token = auth_headers_factory(seeded_standard_user)

    missing_station_response = client.post(
        "/api/reports",
        headers=headers,
        json={
            "station_id": "11111111-1111-1111-1111-111111111111",
            "report_type": "Overheating",
            "severity": 4,
            "description": "The charger overheated during use.",
        },
    )
    assert missing_station_response.status_code == 404
    assert missing_station_response.json()["detail"] == "Station not found"

    invalid_payload_response = client.post(
        "/api/reports",
        headers=headers,
        json={
            "station_id": "not-a-uuid",
            "report_type": "Unknown Category",
            "description": "short",
        },
    )
    assert invalid_payload_response.status_code == 422

    missing_severity_response = client.post(
        "/api/reports",
        headers=headers,
        json={
            "station_id": str(seeded_station.id),
            "report_type": "Overheating",
            "description": "The charger overheated during use.",
        },
    )
    assert missing_severity_response.status_code == 201
    assert missing_severity_response.json()["severity"] is None


def test_reports_support_positive_feedback_and_aliases(client, seeded_standard_user, seeded_station, auth_headers_factory):
    headers, _refresh_token = auth_headers_factory(seeded_standard_user)

    positive_response = client.post(
        "/api/reports",
        headers=headers,
        json={
            "station_id": str(seeded_station.id),
            "report_type": "Positive",
            "description": "Charging worked smoothly with no station-side issues at all.",
        },
    )
    assert positive_response.status_code == 201
    assert positive_response.json()["severity"] is None
    assert positive_response.json()["report_type"] == "Positive"

    alias_response = client.post(
        "/api/reports",
        headers=headers,
        json={
            "station_id": str(seeded_station.id),
            "report_type": "Connectivity / Offline",
            "severity": 3,
            "description": "The station was offline for most of the attempted session.",
        },
    )
    assert alias_response.status_code == 201
    assert alias_response.json()["report_type"] == "Network Outage"


def test_report_access_is_limited_to_owner_or_admin(
    client,
    user_factory,
    station_factory,
    report_factory,
    auth_headers_factory,
):
    owner = user_factory()
    other_user = user_factory()
    admin = user_factory(role=UserRole.admin)
    station = station_factory()
    report = report_factory(user_id=owner.id, station_id=station.id, status=ReportStatus.pending)

    owner_headers, _ = auth_headers_factory(owner)
    other_headers, _ = auth_headers_factory(other_user)
    admin_headers, _ = auth_headers_factory(admin)

    owner_response = client.get(f"/api/reports/{report.id}", headers=owner_headers)
    assert owner_response.status_code == 200

    other_response = client.get(f"/api/reports/{report.id}", headers=other_headers)
    assert other_response.status_code == 403
    assert other_response.json()["detail"] == "Not authorized"

    admin_response = client.get(f"/api/reports/{report.id}", headers=admin_headers)
    assert admin_response.status_code == 200

    not_found_response = client.get(
        "/api/reports/11111111-1111-1111-1111-111111111111",
        headers=owner_headers,
    )
    assert not_found_response.status_code == 404


def test_list_reports_filters_by_status_and_limit(
    client,
    seeded_standard_user,
    seeded_station,
    report_factory,
    auth_headers_factory,
):
    report_factory(user_id=seeded_standard_user.id, station_id=seeded_station.id, status=ReportStatus.pending)
    report_factory(user_id=seeded_standard_user.id, station_id=seeded_station.id, status=ReportStatus.flagged)
    report_factory(user_id=seeded_standard_user.id, station_id=seeded_station.id, status=ReportStatus.resolved)
    headers, _refresh_token = auth_headers_factory(seeded_standard_user)

    filtered_response = client.get(
        "/api/reports",
        headers=headers,
        params={"status_filter": "FLAGGED", "limit": 1},
    )
    assert filtered_response.status_code == 200
    payload = filtered_response.json()
    assert len(payload) == 1
    assert payload[0]["status"] == "FLAGGED"


def test_internal_process_new_feedback_requires_admin_and_returns_result(
    client,
    user_factory,
    station_factory,
    report_factory,
    auth_headers_factory,
):
    admin = user_factory(role=UserRole.admin)
    regular_user = user_factory()
    station = station_factory(risk_score=22.0)
    report = report_factory(user_id=regular_user.id, station_id=station.id, severity=5)

    user_headers, _ = auth_headers_factory(regular_user)
    forbidden_response = client.post(
        "/api/internal/process-new-feedback",
        headers=user_headers,
        json={"report_id": str(report.id), "station_id": str(station.id)},
    )
    assert forbidden_response.status_code == 403

    admin_headers, _ = auth_headers_factory(admin)
    success_response = client.post(
        "/api/internal/process-new-feedback",
        headers=admin_headers,
        json={"report_id": str(report.id), "station_id": str(station.id)},
    )
    assert success_response.status_code == 200
    payload = success_response.json()
    assert payload["status"] == "Processed"
    assert payload["result"]["station_id"] == str(station.id)


def test_admin_station_and_user_edges(client, user_factory, auth_headers_factory):
    admin = user_factory(role=UserRole.admin)
    admin_headers, _ = auth_headers_factory(admin)

    self_deactivate_response = client.delete(f"/api/admin/users/{admin.id}", headers=admin_headers)
    assert self_deactivate_response.status_code == 400
    assert self_deactivate_response.json()["detail"] == "Cannot deactivate yourself"

    missing_user_response = client.delete(
        "/api/admin/users/11111111-1111-1111-1111-111111111111",
        headers=admin_headers,
    )
    assert missing_user_response.status_code == 404

    missing_station_update_response = client.put(
        "/api/stations/11111111-1111-1111-1111-111111111111",
        headers=admin_headers,
        json={"name": "Missing", "latitude": 6.9, "longitude": 79.8},
    )
    assert missing_station_update_response.status_code == 404


def test_admin_report_listing_and_update_require_valid_status(
    client,
    user_factory,
    station_factory,
    report_factory,
    auth_headers_factory,
):
    admin = user_factory(role=UserRole.admin)
    regular_user = user_factory()
    station = station_factory()
    report_factory(user_id=regular_user.id, station_id=station.id, status=ReportStatus.flagged)
    report_factory(user_id=regular_user.id, station_id=station.id, status=ReportStatus.resolved)
    headers, _ = auth_headers_factory(admin)

    list_response = client.get("/api/admin/reports", headers=headers, params={"status_filter": "FLAGGED"})
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["status"] == "FLAGGED"

    invalid_update_response = client.put(
        "/api/reports/11111111-1111-1111-1111-111111111111",
        headers=headers,
        json={"status": "NOT_A_REAL_STATUS"},
    )
    assert invalid_update_response.status_code == 422
