import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from app.models import ChargingStation, Report
from app.services.risk_score_ml_service import risk_scorer

logger = logging.getLogger(__name__)

# ==================== CRITICAL: API KEY PLACEHOLDER ====================
# USER ACTION REQUIRED
# Paste your real OpenChargeMap API key into OPENCHARGEMAP_API_KEY below.
# ======================================================================
OPENCHARGEMAP_API_KEY = "2ae83698-9e83-4234-b647-105f0fe0e089"
OPENCHARGEMAP_BASE_URL = "https://api.openchargemap.io/v3/poi"
OPENCHARGEMAP_COUNTRY_CODE = "LK"


class DataLoaderService:
    POSITIVE_FEEDBACK_PHRASES = (
        "working fine",
        "works fine",
        "no issues",
        "no issue",
        "all good",
        "operating normally",
        "working well",
        "runs smoothly",
        "charging successfully",
        "stable session",
    )
    NEGATIVE_FEEDBACK_PHRASES = (
        "not working",
        "no power",
        "power failure",
        "sparks",
        "spark",
        "overheating",
        "overheated",
        "broken",
        "burning smell",
        "electric shock",
        "smoke",
        "fire",
        "damaged",
        "offline",
        "unstable",
        "tripped",
        "fault",
        "failed",
        "failure",
    )

    @staticmethod
    def analyze_feedback_signal(description: str, severity: Optional[int] = None) -> Dict[str, Any]:
        text = (description or "").strip().lower()
        if not text:
            return {"score": 0.0, "label": "neutral"}

        signal = 0.0
        sanitized_text = text

        for phrase in DataLoaderService.POSITIVE_FEEDBACK_PHRASES:
            if phrase in sanitized_text:
                signal -= 0.35
                sanitized_text = sanitized_text.replace(phrase, " ")

        for phrase in DataLoaderService.NEGATIVE_FEEDBACK_PHRASES:
            if phrase in sanitized_text:
                signal += 0.45
                sanitized_text = sanitized_text.replace(phrase, " ")

        positive_tokens = {
            "good", "great", "smooth", "stable", "safe", "normal", "fine", "resolved", "healthy", "ok", "okay"
        }
        negative_tokens = {
            "broken", "faulty", "fault", "hot", "overheat", "sparking", "burnt", "error", "damaged", "unsafe",
            "unstable", "shock", "smoke", "alarm", "fail", "failed"
        }

        for token in sanitized_text.split():
            normalized = token.strip(".,!?:;()[]{}\"'")
            if normalized in positive_tokens:
                signal -= 0.12
            elif normalized in negative_tokens:
                signal += 0.18

        severity_value = severity or 0
        if severity_value >= 4:
            signal += 0.15
        elif severity_value <= 2 and signal < 0:
            signal -= 0.08

        signal = max(-1.0, min(1.0, signal))
        if signal >= 0.2:
            label = "negative"
        elif signal <= -0.2:
            label = "positive"
        else:
            label = "neutral"

        return {
            "score": round(signal, 3),
            "label": label,
        }

    @staticmethod
    def get_newest_review(db: Session, station_id: Any) -> Optional[Report]:
        return (
            db.query(Report)
            .filter(Report.station_id == station_id)
            .order_by(Report.created_at.desc())
            .first()
        )

    @staticmethod
    def get_station_summary(db: Session, station_id: Any) -> Dict[str, Any]:
        reports = db.query(Report).filter(Report.station_id == station_id).all()
        review_count = len(reports)
        if review_count == 0:
            return {
                "review_count": 0,
                "bad_review_ratio": 0.0,
                "avg_rating": 3.0,
                "avg_keyword_count": 0.0,
            }

        bad_reviews = sum(1 for report in reports if (report.severity or 0) >= 3)
        bad_review_ratio = bad_reviews / review_count
        avg_rating = max(1.0, 5.0 - (sum(report.severity or 0 for report in reports) / review_count))
        avg_keyword_count = sum(len((report.description or "").split()) for report in reports) / review_count
        return {
            "review_count": review_count,
            "bad_review_ratio": bad_review_ratio,
            "avg_rating": avg_rating,
            "avg_keyword_count": avg_keyword_count,
        }

    @staticmethod
    def map_database_to_features(
        db: Session,
        station: ChargingStation,
        report: Optional[Report] = None,
    ) -> Dict[str, Any]:
        summary = DataLoaderService.get_station_summary(db, station.id)
        bad_ratio = summary["bad_review_ratio"]

        try:
            review_modifier = 0.01 + 4.98 / (1.0 + math.exp(-10.0 * (bad_ratio - 0.5)))
        except OverflowError:
            review_modifier = 0.01 if bad_ratio < 0.5 else 4.99

        description = (report.description if report else "") or ""
        feedback_signal = DataLoaderService.analyze_feedback_signal(
            description,
            severity=(report.severity if report else None),
        )

        return {
            "max_charge_power": station.charging_power_kw or 7.0,
            "EV Level2 EVSE Num": 1,
            "RapidCharge": 1 if (station.charging_power_kw or 0) > 50 else 0,
            "Component": "Unknown",
            "kWhDelivered": 20.0,
            "Manufacturer": station.operator or "Unknown",
            "FastCharge": 1 if (station.charging_power_kw or 0) > 22 else 0,
            "vehicle_model": "Unknown",
            "chargingDuration": 2.0,
            "station": station.name or "Unknown Station",
            "PlugType": station.connector_types or "Unknown",
            "avg_rating": summary["avg_rating"],
            "review_count": summary["review_count"],
            "bad_review_ratio": summary["bad_review_ratio"],
            "avg_keyword_count": summary["avg_keyword_count"] or len(description.split()),
            "review_risk_modifier": review_modifier,
            "feedback_signal_score": feedback_signal["score"],
            "feedback_signal_label": feedback_signal["label"],
        }

    @staticmethod
    def fetch_openchargemap_for_sri_lanka() -> List[Dict[str, Any]]:
        if OPENCHARGEMAP_API_KEY == "PASTE_YOUR_API_KEY_HERE":
            raise RuntimeError(
                "OpenChargeMap API key is missing. Update OPENCHARGEMAP_API_KEY in backend/app/services/data_loader_service.py."
            )

        params = {
            "countrycode": OPENCHARGEMAP_COUNTRY_CODE,
            "maxresults": 500,
            "compact": "false",
            "verbose": "false",
            "key": OPENCHARGEMAP_API_KEY,
        }

        response = requests.get(OPENCHARGEMAP_BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        raw_stations = response.json()

        normalized_stations: List[Dict[str, Any]] = []
        for station_data in raw_stations:
            address_info = station_data.get("AddressInfo") or {}
            latitude = address_info.get("Latitude")
            longitude = address_info.get("Longitude")
            if latitude is None or longitude is None:
                logger.warning("Skipping OpenChargeMap station %s without coordinates", station_data.get("ID"))
                continue

            connector_titles: List[str] = []
            max_power_kw: Optional[float] = None
            for connection in station_data.get("Connections") or []:
                connector_title = ((connection.get("ConnectionType") or {}).get("Title")) or "Unknown"
                if connector_title not in connector_titles:
                    connector_titles.append(connector_title)

                power_kw = connection.get("PowerKW")
                if isinstance(power_kw, (int, float)) and power_kw > 0:
                    max_power_kw = power_kw if max_power_kw is None else max(max_power_kw, power_kw)

            normalized_stations.append(
                {
                    "ocm_id": station_data.get("ID"),
                    "name": address_info.get("Title") or "Unnamed Station",
                    "latitude": latitude,
                    "longitude": longitude,
                    "address": address_info.get("AddressLine1"),
                    "city": address_info.get("Town") or address_info.get("StateOrProvince"),
                    "operator": ((station_data.get("OperatorInfo") or {}).get("Title")) or "Unknown",
                    "connector_types": ", ".join(connector_titles) if connector_titles else "Unknown",
                    "charging_power_kw": max_power_kw or 7.0,
                    "status": "operational",
                }
            )

        logger.info("Fetched %s Sri Lanka stations from OpenChargeMap", len(normalized_stations))
        return normalized_stations

    @staticmethod
    def _upsert_station(db: Session, station_data: Dict[str, Any], force_update: bool) -> tuple[ChargingStation, bool, bool]:
        existing_station = db.query(ChargingStation).filter(
            ChargingStation.latitude == station_data["latitude"],
            ChargingStation.longitude == station_data["longitude"],
        ).first()

        created = False
        updated = False

        if existing_station is None:
            existing_station = ChargingStation(
                name=station_data["name"],
                latitude=station_data["latitude"],
                longitude=station_data["longitude"],
                address=station_data["address"],
                city=station_data["city"],
                operator=station_data["operator"],
                connector_types=station_data["connector_types"],
                charging_power_kw=station_data["charging_power_kw"],
                status=station_data["status"],
            )
            db.add(existing_station)
            db.flush()
            created = True
        else:
            station_changed = (
                force_update
                or existing_station.name != station_data["name"]
                or existing_station.address != station_data["address"]
                or existing_station.city != station_data["city"]
                or existing_station.operator != station_data["operator"]
                or existing_station.connector_types != station_data["connector_types"]
                or existing_station.charging_power_kw != station_data["charging_power_kw"]
            )
            if station_changed:
                existing_station.name = station_data["name"]
                existing_station.address = station_data["address"]
                existing_station.city = station_data["city"]
                existing_station.operator = station_data["operator"]
                existing_station.connector_types = station_data["connector_types"]
                existing_station.charging_power_kw = station_data["charging_power_kw"]
                existing_station.updated_at = datetime.utcnow()
                updated = True

        return existing_station, created, updated

    @staticmethod
    def _apply_risk_score(station: ChargingStation, risk_score: float) -> str:
        station.safety_score = risk_score
        station.last_scored_at = datetime.utcnow()

        if risk_score < 30:
            risk_level = "LOW"
        elif risk_score <= 70:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"

        try:
            # Persist the uppercase enum value expected by the existing PostgreSQL enum.
            station.cyber_risk_level = risk_level
        except Exception:
            logger.debug("Could not assign cyber risk enum for station %s", station.name, exc_info=True)

        return risk_level

    @staticmethod
    def build_station_payload(station: ChargingStation) -> Dict[str, Any]:
        payload = {
            "id": str(station.id),
            "name": station.name,
            "latitude": station.latitude,
            "longitude": station.longitude,
            "city": station.city,
            "address": station.address,
            "operator": station.operator,
            "connector_types": station.connector_types,
            "charging_power_kw": station.charging_power_kw,
            "status": station.status,
            "risk_score": station.risk_score,
            "cyber_risk_level": station.cyber_risk_level,
            "last_scored_at": station.last_scored_at,
        }
        return risk_scorer.enrich_station_with_color(payload)

    @staticmethod
    def sync_openchargemap_to_database(db: Session, force_update: bool = False) -> Dict[str, Any]:
        stats = {
            "fetched": 0,
            "created": 0,
            "updated": 0,
            "scored": 0,
            "failed": 0,
            "timestamp": datetime.utcnow().isoformat(),
        }
        station_payloads: List[Dict[str, Any]] = []

        try:
            ocm_stations = DataLoaderService.fetch_openchargemap_for_sri_lanka()
            stats["fetched"] = len(ocm_stations)

            for station_data in ocm_stations:
                try:
                    station, created, updated = DataLoaderService._upsert_station(
                        db,
                        station_data,
                        force_update=force_update,
                    )
                    if created:
                        stats["created"] += 1
                    if updated:
                        stats["updated"] += 1

                    latest_report = DataLoaderService.get_newest_review(db, station.id)
                    feature_payload = DataLoaderService.map_database_to_features(
                        db,
                        station,
                        report=latest_report,
                    )
                    risk_score = risk_scorer.calculate_latest_risk_score(feature_payload)
                    DataLoaderService._apply_risk_score(station, risk_score)
                    stats["scored"] += 1
                    station_payloads.append(DataLoaderService.build_station_payload(station))
                except Exception as station_exc:
                    stats["failed"] += 1
                    logger.exception(
                        "Failed to sync OpenChargeMap station %s: %s",
                        station_data.get("ocm_id"),
                        station_exc,
                    )

            db.commit()
            logger.info(
                "OpenChargeMap sync complete. fetched=%s created=%s updated=%s scored=%s failed=%s",
                stats["fetched"],
                stats["created"],
                stats["updated"],
                stats["scored"],
                stats["failed"],
            )
        except Exception as exc:
            db.rollback()
            stats["error"] = str(exc)
            logger.exception("OpenChargeMap synchronization failed: %s", exc)

        stats["stations"] = station_payloads
        return stats
