from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import (
    ChargingStation,
    CyberRiskLevel,
    ScoreHistory,
    StationStatus,
    TemperatureHistory,
)


SEED_STATIONS = [
    {
        "name": "Colombo Fast Charge",
        "latitude": 6.9147,
        "longitude": 79.8512,
        "city": "Colpetty",
        "address": "Colpetty, Colombo",
        "operator": "ChargeSafe SL",
        "connector_types": "CCS2, Type 2",
        "charging_power_kw": 120,
        "status": StationStatus.operational,
        "safety_score": 82,
        "cyber_risk_level": CyberRiskLevel.low,
        "firmware_version": "v2.1.0",
        "firmware_age_days": 15,
        "temperature_celsius": 33,
        "power_status": "Stable",
        "fault_count": 0,
    },
    {
        "name": "Galle Rd Charger",
        "latitude": 6.0333,
        "longitude": 80.2167,
        "city": "Galle",
        "address": "Galle Road, Galle",
        "operator": "ChargeSafe SL",
        "connector_types": "CCS2",
        "charging_power_kw": 60,
        "status": StationStatus.faulty,
        "safety_score": 68,
        "cyber_risk_level": CyberRiskLevel.medium,
        "firmware_version": "v1.4.1",
        "firmware_age_days": 60,
        "temperature_celsius": 39,
        "power_status": "Fluctuation",
        "fault_count": 2,
    },
    {
        "name": "Kandy Central EV",
        "latitude": 7.2906,
        "longitude": 80.6337,
        "city": "Kandy",
        "address": "Kandy Central, Kandy",
        "operator": "ChargeSafe SL",
        "connector_types": "CCS2, CHAdeMO",
        "charging_power_kw": 50,
        "status": StationStatus.maintenance,
        "safety_score": 32,
        "cyber_risk_level": CyberRiskLevel.critical,
        "firmware_version": "v1.2.0",
        "firmware_age_days": 180,
        "temperature_celsius": 58,
        "power_status": "Unstable",
        "fault_count": 5,
    },
    {
        "name": "Negombo Hub",
        "latitude": 7.2008,
        "longitude": 79.8737,
        "city": "Negombo",
        "address": "Negombo Hub, Negombo",
        "operator": "ChargeSafe SL",
        "connector_types": "CCS2, Type 2",
        "charging_power_kw": 90,
        "status": StationStatus.operational,
        "safety_score": 91,
        "cyber_risk_level": CyberRiskLevel.low,
        "firmware_version": "v2.0.1",
        "firmware_age_days": 25,
        "temperature_celsius": 31,
        "power_status": "Stable",
        "fault_count": 0,
    },
    {
        "name": "Jaffna North",
        "latitude": 9.6615,
        "longitude": 80.0255,
        "city": "Jaffna",
        "address": "Jaffna North, Jaffna",
        "operator": "ChargeSafe SL",
        "connector_types": "CCS2",
        "charging_power_kw": 75,
        "status": StationStatus.operational,
        "safety_score": 78,
        "cyber_risk_level": CyberRiskLevel.low,
        "firmware_version": "v1.8.0",
        "firmware_age_days": 45,
        "temperature_celsius": 30,
        "power_status": "Stable",
        "fault_count": 1,
    },
]


def seed_initial_data(db: Session) -> None:
    if db.query(ChargingStation).first():
        return

    now = datetime.utcnow()
    level_map = {82: "SAFE", 68: "WARN", 32: "CRIT", 91: "SAFE", 78: "SAFE"}

    for item in SEED_STATIONS:
        station = ChargingStation(**item, last_scored_at=now)
        db.add(station)
        db.flush()

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
                    level=level_map.get(base_score, "WARN"),
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

    db.commit()
