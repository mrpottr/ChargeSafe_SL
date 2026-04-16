import logging
import uuid
from datetime import datetime
from typing import Any, Dict

from backend.services.data_loader_service import DataLoaderService
from backend.services.risk_score_ml_service import risk_score_ml_service
from backend.services.training_service import TrainingService

logger = logging.getLogger(__name__)


class FeedbackProcessor:
    """Glue layer for the isolated asynchronous continuous-learning workflow."""

    @staticmethod
    def on_new_review_received(review_payload: Dict[str, Any], db: Any) -> Dict[str, Any]:
        from app.models import ChargingStation, Report, ScoreHistory

        report_id = review_payload.get("report_id") or review_payload.get("review_id")
        station_id = review_payload.get("station_id")

        report = None
        if report_id is not None:
            report = db.query(Report).filter(Report.id == report_id).first()

        if report is None and station_id is not None:
            report = DataLoaderService.get_newest_review(db, station_id)

        if report is None:
            raise ValueError("No review row could be resolved for the feedback payload.")

        station = db.query(ChargingStation).filter(ChargingStation.id == report.station_id).first()
        if station is None:
            raise ValueError("Charging station could not be resolved for the review row.")

        feature_payload = DataLoaderService.map_database_to_features(db, report, station)
        new_risk_score = risk_score_ml_service.calculate_latest_risk_score(feature_payload)
        risk_score_ml_service.assign_station_risk_fields(station, new_risk_score)

        risk_status = risk_score_ml_service.get_risk_status(new_risk_score)
        db.add(
            ScoreHistory(
                id=uuid.uuid4(),
                station_id=station.id,
                score=new_risk_score,
                level=risk_status.upper().replace(" RISK", ""),
                trigger="Auto(ML)",
                recorded_at=datetime.utcnow(),
            )
        )
        db.commit()

        training_result = TrainingService.trigger_incremental_update(
            new_review_data={
                "review_text": report.description or "",
                "station_id": str(station.id),
                "report_id": str(report.id),
            },
            new_review_label=TrainingService._derive_label_from_review(report),
            db=db,
        )

        logger.info(
            "Continuous-learning pipeline processed review %s for station %s with risk score %s",
            report.id,
            station.id,
            new_risk_score,
        )
        return {
            "report_id": str(report.id),
            "station_id": str(station.id),
            "risk_score": new_risk_score,
            "risk_status": risk_status,
            "training": training_result,
        }
