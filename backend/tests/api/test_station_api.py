from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import CyberScore
from tests.factories import DEFAULT_PASSWORD


def test_list_stations_filters_and_enriches_response(client, station_factory):
    station_factory(name="Colombo Match", city="Colombo", risk_score=58, latitude=6.90, longitude=79.85)
    station_factory(name="Colombo Low", city="Colombo", risk_score=18, latitude=6.91, longitude=79.86)
    station_factory(name="Galle Match", city="Galle", risk_score=62, latitude=6.03, longitude=80.21)

    response = client.get(
        "/api/stations",
        params={
            "city": "Colombo",
            "min_score": 40,
            "max_score": 70,
            "status_filter": "operational",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["name"] == "Colombo Match"
    assert payload[0]["risk_level"] == "Medium Risk"


def test_station_detail_and_history_endpoints(client, seeded_station, score_history_factory, temperature_history_factory):
    now = datetime.utcnow()
    score_history_factory(
        station_id=seeded_station.id,
        score=40.0,
        level="MEDIUM",
        trigger="System",
        recorded_at=now - timedelta(days=2),
    )
    score_history_factory(
        station_id=seeded_station.id,
        score=55.0,
        level="MEDIUM",
        trigger="Auto",
        recorded_at=now - timedelta(days=1),
    )
    temperature_history_factory(
        station_id=seeded_station.id,
        temperature_celsius=31.5,
        recorded_at=now - timedelta(days=1),
    )
    temperature_history_factory(
        station_id=seeded_station.id,
        temperature_celsius=34.0,
        recorded_at=now,
    )

    detail_response = client.get(f"/api/stations/{seeded_station.id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["id"] == str(seeded_station.id)
    assert detail_payload["risk_level"]

    score_history_response = client.get(f"/api/stations/{seeded_station.id}/score-history", params={"days": 7})
    assert score_history_response.status_code == 200
    score_history_payload = score_history_response.json()
    assert [item["score"] for item in score_history_payload] == [40.0, 55.0]

    temperature_history_response = client.get(
        f"/api/stations/{seeded_station.id}/temperature-history",
        params={"days": 7},
    )
    assert temperature_history_response.status_code == 200
    temperature_history_payload = temperature_history_response.json()
    assert [item["temperature"] for item in temperature_history_payload] == [31.5, 34.0]

    invalid_uuid_response = client.get("/api/stations/not-a-uuid")
    assert invalid_uuid_response.status_code == 422


def test_cyber_score_requires_auth_and_returns_weighted_breakdown(
    client,
    seeded_station,
    user_factory,
    auth_headers_factory,
    cyber_criterion_factory,
    db_session: Session,
):
    criterion_a = cyber_criterion_factory(criterion_name="Firmware", weight=2.0)
    criterion_b = cyber_criterion_factory(criterion_name="Network", weight=1.0)

    db_session.add(
        CyberScore(
            station_id=seeded_station.id,
            criterion_id=criterion_a.id,
            score_value=4,
            risk_rating="HIGH",
            notes="Outdated firmware",
        )
    )
    db_session.add(
        CyberScore(
            station_id=seeded_station.id,
            criterion_id=criterion_b.id,
            score_value=2,
            risk_rating="MEDIUM",
            notes="Intermittent network issues",
        )
    )
    db_session.commit()

    unauthenticated_response = client.get(f"/api/stations/{seeded_station.id}/cyber-score")
    assert unauthenticated_response.status_code == 401

    user = user_factory(password=DEFAULT_PASSWORD)
    headers, _refresh_token = auth_headers_factory(user)

    response = client.get(f"/api/stations/{seeded_station.id}/cyber-score", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["station_id"] == str(seeded_station.id)
    assert payload["criteria_count"] == 2
    assert payload["overall_score"] == 83.3
    assert payload["overall_risk_level"] == "HIGH"
    assert [item["criterion_name"] for item in payload["breakdown"]] == ["Firmware", "Network"]


def test_station_not_found_and_days_validation(client):
    missing_station_id = "11111111-1111-1111-1111-111111111111"

    missing_station_response = client.get(f"/api/stations/{missing_station_id}")
    assert missing_station_response.status_code == 404

    invalid_days_response = client.get(
        f"/api/stations/{missing_station_id}/score-history",
        params={"days": 0},
    )
    assert invalid_days_response.status_code == 422
