import os
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import (
    ChargingStation,
    CyberRiskLevel,
    ScoreHistory,
    StationStatus,
    TemperatureHistory,
    User,
    UserRole,
)
from app.core.security import hash_password


REMOVED_STATION_NAMES = {
    "Colombo Fast Charge",
    "Galle Rd Charger",
    "Kandy Central EV",
    "Negombo Hub",
    "Jaffna North",
}


SEED_STATIONS = [
    {
        "name": "DEMO Colombo High Risk 01",
        "latitude": 6.9123,
        "longitude": 79.8567,
        "city": "Colombo",
        "address": "Demo Address 1",
        "operator": "ChargeSafe Demo",
        "connector_types": "CCS2, Type 2",
        "charging_power_kw": 120,
        "status": StationStatus.faulty,
        "safety_score": 88,
        "cyber_risk_level": CyberRiskLevel.high,
        "firmware_version": "v1.0.2",
        "firmware_age_days": 365,
        "temperature_celsius": 52,
        "power_status": "Unstable",
        "fault_count": 5,
    },
    {
        "name": "DEMO Kandy High Risk 02",
        "latitude": 7.2911,
        "longitude": 80.6350,
        "city": "Kandy",
        "address": "Demo Address 2",
        "operator": "ChargeSafe Demo",
        "connector_types": "CCS2, CHAdeMO",
        "charging_power_kw": 90,
        "status": StationStatus.maintenance,
        "safety_score": 81,
        "cyber_risk_level": CyberRiskLevel.high,
        "firmware_version": "v1.1.0",
        "firmware_age_days": 320,
        "temperature_celsius": 49,
        "power_status": "Fluctuation",
        "fault_count": 4,
    },
    {
        "name": "DEMO Galle Medium Risk 01",
        "latitude": 6.0310,
        "longitude": 80.2175,
        "city": "Galle",
        "address": "Demo Address 3",
        "operator": "ChargeSafe Demo",
        "connector_types": "CCS2",
        "charging_power_kw": 60,
        "status": StationStatus.operational,
        "safety_score": 62,
        "cyber_risk_level": CyberRiskLevel.medium,
        "firmware_version": "v1.8.0",
        "firmware_age_days": 180,
        "temperature_celsius": 38,
        "power_status": "Stable",
        "fault_count": 2,
    },
    {
        "name": "DEMO Kurunegala Medium Risk 02",
        "latitude": 7.4862,
        "longitude": 80.3647,
        "city": "Kurunegala",
        "address": "Demo Address 4",
        "operator": "ChargeSafe Demo",
        "connector_types": "CCS2, Type 2",
        "charging_power_kw": 50,
        "status": StationStatus.operational,
        "safety_score": 45,
        "cyber_risk_level": CyberRiskLevel.medium,
        "firmware_version": "v1.9.1",
        "firmware_age_days": 120,
        "temperature_celsius": 35,
        "power_status": "Stable",
        "fault_count": 1,
    },
    {
        "name": "DEMO Jaffna Low Risk 01",
        "latitude": 9.6680,
        "longitude": 80.0201,
        "city": "Jaffna",
        "address": "Demo Address 5",
        "operator": "ChargeSafe Demo",
        "connector_types": "CCS2",
        "charging_power_kw": 75,
        "status": StationStatus.operational,
        "safety_score": 22,
        "cyber_risk_level": CyberRiskLevel.low,
        "firmware_version": "v2.3.0",
        "firmware_age_days": 45,
        "temperature_celsius": 29,
        "power_status": "Stable",
        "fault_count": 0,
    },
    {
        "name": "DEMO Matara Low Risk 02",
        "latitude": 5.9485,
        "longitude": 80.5353,
        "city": "Matara",
        "address": "Demo Address 6",
        "operator": "ChargeSafe Demo",
        "connector_types": "CCS2, Type 2",
        "charging_power_kw": 60,
        "status": StationStatus.operational,
        "safety_score": 15,
        "cyber_risk_level": CyberRiskLevel.low,
        "firmware_version": "v2.4.1",
        "firmware_age_days": 20,
        "temperature_celsius": 28,
        "power_status": "Stable",
        "fault_count": 0,
    },
]


def seed_initial_data(db: Session) -> None:
    # This seeding routine keeps the demo dataset predictable by removing retired
    # placeholders, upserting the curated stations, and backfilling history rows.
    now = datetime.utcnow()

    stale_stations = db.query(ChargingStation).filter(ChargingStation.name.in_(REMOVED_STATION_NAMES)).all()
    for stale_station in stale_stations:
        db.delete(stale_station)
    if stale_stations:
        db.flush()

    def level_for_score(score: float) -> str:
        if score <= 30:
            return "LOW"
        if score <= 70:
            return "MEDIUM"
        return "HIGH"

    for item in SEED_STATIONS:
        station = db.query(ChargingStation).filter(
            ChargingStation.latitude == item["latitude"],
            ChargingStation.longitude == item["longitude"],
        ).first()

        if station is None:
            station = ChargingStation(**item, last_scored_at=now)
            db.add(station)
            db.flush()
        else:
            for field, value in item.items():
                setattr(station, field, value)
            station.last_scored_at = now
            station.updated_at = now

        has_score_history = db.query(ScoreHistory.id).filter(ScoreHistory.station_id == station.id).first()
        has_temperature_history = db.query(TemperatureHistory.id).filter(
            TemperatureHistory.station_id == station.id
        ).first()

        if has_score_history and has_temperature_history:
            continue

        base_score = item["safety_score"] or 0
        for days_ago, score_offset, temp_offset in [
            (3, -4, -1.5),
            (2, -2, 0),
            (1, 1, 1.2),
            (0, 0, 0.6),
        ]:
            recorded_at = now - timedelta(days=days_ago)
            score = max(0, min(100, base_score + score_offset))
            db.add(
                ScoreHistory(
                    station_id=station.id,
                    score=score,
                    level=level_for_score(score),
                    trigger="System" if days_ago else "Auto",
                    recorded_at=recorded_at,
                )
            )
            db.add(
                TemperatureHistory(
                    station_id=station.id,
                    temperature_celsius=(item["temperature_celsius"] or 30) + temp_offset,
                    recorded_at=recorded_at,
                )
            )

    admin_email = "admin@chargesafe.app"

    # The bootstrap step also guarantees the default admin account exists so a
    # fresh environment does not get stuck before the first login.
    existing_admin = db.query(User).filter(User.username == "admin").first()
    if not existing_admin:
        admin_password = os.environ.get("ADMIN_PASSWORD", "")
        if not admin_password:
            raise RuntimeError(
                "ADMIN_PASSWORD environment variable is not set. "
                "Set it in your .env file before starting the server."
            )
        admin_user = User(
            username="admin",
            email=admin_email,
            password_hash=hash_password(admin_password),
            role=UserRole.admin,
            is_active=True,
            email_verified=True,
        )
        db.add(admin_user)
    elif existing_admin.email == "admin@chargesafe.local":
        existing_admin.email = admin_email

    db.commit()
