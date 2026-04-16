import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from app.models import ChargingStation, Report

from backend.services.risk_score_ml_service import risk_score_ml_service

logger = logging.getLogger(__name__)

# ==================== CRITICAL: API KEY PLACEHOLDER ====================
# USER ACTION REQUIRED
# Paste your real OpenChargeMap API key into OPENCHARGEMAP_API_KEY below.
# ======================================================================
OPENCHARGEMAP_API_KEY = "PASTE_YOUR_API_KEY_HERE"
OPENCHARGEMAP_BASE_URL = "https://api.openchargemap.io/v3/poi"
OPENCHARGEMAP_COUNTRY_CODE = "LK"


class DataLoaderService:
    """Data access and feature mapping helpers for the isolated ML pipeline."""

    @staticmethod
    def get_newest_review(db: Session, charging_station_id: Any) -> Optional[Report]:
        """
        Return the latest review row for a charging station using the existing ORM.
        """
        return (
            db.query(Report)
            .filter(Report.station_id == charging_station_id)
            .order_by(Report.created_at.desc())
            .first()
        )

    @staticmethod
    def get_recent_reviews(db: Session, num_samples: int = 100) -> List[Report]:
        """
        Return a replay window of recent reviews for lightweight incremental updates.
        """
        return (
            db.query(Report)
            .order_by(Report.created_at.desc())
            .limit(num_samples)
            .all()
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
    def build_feature_payload(
        db: Session,
        station: ChargingStation,
        latest_report: Optional[Report] = None,
    ) -> Dict[str, Any]:
        """
        Build a feature dictionary that matches backend/models/feature_names.json.
        """
        summary = DataLoaderService.get_station_summary(db, station.id)
        bad_ratio = summary["bad_review_ratio"]

        try:
            review_modifier = 0.01 + 4.98 / (1.0 + math.exp(-10.0 * (bad_ratio - 0.5)))
        except OverflowError:
            review_modifier = 0.01 if bad_ratio < 0.5 else 4.99

        description = (latest_report.description if latest_report else "") or ""

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
        }

    @staticmethod
    def map_database_to_features(
        db: Session,
        db_result: Any,
        station: Optional[ChargingStation] = None,
    ) -> Dict[str, Any]:
        """
        Convert existing ORM rows into the structured feature dictionary expected by the ML service.

        Supported call patterns:
        - map_database_to_features(db, report_row, station_row)
        - map_database_to_features(db, station_row)
        """
        if isinstance(db_result, Report):
            report = db_result
            active_station = station
            if active_station is None:
                active_station = (
                    db.query(ChargingStation)
                    .filter(ChargingStation.id == report.station_id)
                    .first()
                )
            if active_station is None:
                raise ValueError("Charging station not found for review row.")
            return DataLoaderService.build_feature_payload(db, active_station, latest_report=report)

        if isinstance(db_result, ChargingStation):
            return DataLoaderService.build_feature_payload(db, db_result, latest_report=None)

        raise TypeError("db_result must be a Report or ChargingStation ORM row.")

    @staticmethod
    def fetch_openchargemap_for_sri_lanka() -> List[Dict[str, Any]]:
        if OPENCHARGEMAP_API_KEY == "PASTE_YOUR_API_KEY_HERE":
            raise RuntimeError(
                "OpenChargeMap API key is missing. Update OPENCHARGEMAP_API_KEY in backend/services/data_loader_service.py."
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
                logger.warning("Skipping OCM station %s without coordinates", station_data.get("ID"))
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
                    "source": "OpenChargeMap",
                }
            )

        logger.info("Fetched %s Sri Lanka stations from OpenChargeMap", len(normalized_stations))
        return normalized_stations

    @staticmethod
    def upsert_station(db: Session, station_data: Dict[str, Any], force_update: bool = False) -> ChargingStation:
        existing_station = db.query(ChargingStation).filter(
            ChargingStation.latitude == station_data["latitude"],
            ChargingStation.longitude == station_data["longitude"],
        ).first()

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
            return existing_station

        if force_update:
            existing_station.name = station_data["name"]
            existing_station.address = station_data["address"]
            existing_station.city = station_data["city"]
            existing_station.operator = station_data["operator"]
            existing_station.connector_types = station_data["connector_types"]
            existing_station.charging_power_kw = station_data["charging_power_kw"]
            existing_station.updated_at = datetime.utcnow()

        return existing_station

    @staticmethod
    def score_station_in_real_time(db: Session, station: ChargingStation) -> float:
        latest_report = (
            db.query(Report)
            .filter(Report.station_id == station.id)
            .order_by(Report.created_at.desc())
            .first()
        )
        feature_payload = DataLoaderService.build_feature_payload(db, station, latest_report=latest_report)
        risk_score = risk_score_ml_service.calculate_latest_risk_score(feature_payload)
        risk_score_ml_service.assign_station_risk_fields(station, risk_score)
        return risk_score

    @staticmethod
    def build_station_payload(station: ChargingStation) -> Dict[str, Any]:
        station_payload = {
            "id": str(station.id),
            "name": station.name,
            "latitude": station.latitude,
            "longitude": station.longitude,
            "address": station.address,
            "city": station.city,
            "operator": station.operator,
            "connector_types": station.connector_types,
            "charging_power_kw": station.charging_power_kw,
            "status": station.status.value if hasattr(station.status, "value") else station.status,
            "risk_score": station.risk_score,
            "last_scored_at": station.last_scored_at.isoformat() if station.last_scored_at else None,
        }
        return risk_score_ml_service.build_visualization_payload(station_payload)

    @staticmethod
    def sync_openchargemap_to_database(db: Session, force_update: bool = False) -> Dict[str, Any]:
        """
        Fetch Sri Lanka stations, map them into existing ORM models, and compute
        the hybrid ML risk score immediately for every processed station.
        """
        stats = {
            "fetched": 0,
            "created": 0,
            "updated": 0,
            "scored": 0,
            "failed": 0,
            "timestamp": datetime.utcnow().isoformat(),
        }
        visualization_payload: List[Dict[str, Any]] = []

        try:
            ocm_stations = DataLoaderService.fetch_openchargemap_for_sri_lanka()
            stats["fetched"] = len(ocm_stations)

            for station_data in ocm_stations:
                try:
                    existing_station = db.query(ChargingStation).filter(
                        ChargingStation.latitude == station_data["latitude"],
                        ChargingStation.longitude == station_data["longitude"],
                    ).first()

                    station = DataLoaderService.upsert_station(db, station_data, force_update=force_update)

                    if existing_station is None:
                        stats["created"] += 1
                    elif force_update:
                        stats["updated"] += 1

                    DataLoaderService.score_station_in_real_time(db, station)
                    stats["scored"] += 1
                    visualization_payload.append(DataLoaderService.build_station_payload(station))
                except Exception as station_exc:
                    stats["failed"] += 1
                    logger.exception(
                        "Failed to sync and score station %s: %s",
                        station_data.get("ocm_id"),
                        station_exc,
                    )

            db.commit()
        except Exception as exc:
            db.rollback()
            stats["error"] = str(exc)
            logger.exception("OpenChargeMap synchronization failed: %s", exc)

        stats["stations"] = visualization_payload
        return stats
