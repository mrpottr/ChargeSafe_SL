from datetime import datetime

from sqlalchemy.orm import Session

from app.models import ChargingStation, Report, ScoreHistory
from app.services.data_loader_service import DataLoaderService
from app.services.risk_state_observer import notify_on_risk_state_change
from app.services.risk_score_ml_service import risk_scorer


class FeedbackProcessor:
    # This processor turns a newly submitted report into an immediate rescoring
    # pass so the station view and notification stream update without a reload.
    @staticmethod
    def process_feedback(report_id: str, station_id: str, db: Session):
        """
        Calculates the latest hybrid ML score and persists it immediately so the UI can
        reflect the updated station state without waiting for a page reload.
        1. Calculates new ML risk score using RiskScoreMLService.
        2. Updates the Database explicitly.
        """
        try:
            print(f"FeedbackProcessor: Processing new review for station {station_id}")
            report = db.query(Report).filter(Report.id == report_id).first()
            station = db.query(ChargingStation).filter(ChargingStation.id == station_id).first()
            
            if not report or not station:
                print("FeedbackProcessor: Report or Station missing. Aborting.")
                return
            
            # The recalculation happens before the commit so the updated score,
            # history entry, and notification decision all stay in one transaction.
            previous_risk_score = station.safety_score
            features_dict = DataLoaderService.map_database_to_features(db, station, report)
            new_risk_score = risk_scorer.calculate_latest_risk_score(features_dict)
            
            # Updating the live station row immediately keeps follow-up fetches in
            # sync with the just-submitted report.
            station.safety_score = new_risk_score
            station.last_scored_at = datetime.utcnow()
            
            # The UI still expects the familiar LOW, MEDIUM, and HIGH labels, so
            # the numeric score is translated back into that banding here.
            if new_risk_score <= 30: new_risk_level = "LOW"
            elif new_risk_score <= 70: new_risk_level = "MEDIUM"
            else: new_risk_level = "HIGH"
            
            # History rows preserve each automated rescore so the station charts
            # can explain why the current score moved.
            import uuid
            score_history = ScoreHistory(
                id=uuid.uuid4(),
                station_id=station.id,
                score=new_risk_score,
                level=new_risk_level,
                trigger="Auto(ML)"
            )
            db.add(score_history)
            
            # The overall cyber badge is kept aligned with the latest score so the
            # frontend does not have to guess how to map the updated value.
            station.cyber_risk_level = new_risk_level

            notify_on_risk_state_change(
                db,
                station_id=station.id,
                old_score=previous_risk_score,
                new_score=new_risk_score,
                timestamp=station.last_scored_at,
            )
            
            db.commit()
            print(f"FeedbackProcessor: Station {station_id} ML risk score updated to {new_risk_score}")
            return {
                "station_id": str(station.id),
                "risk_score": new_risk_score,
                "cyber_risk_level": new_risk_level,
                "last_scored_at": station.last_scored_at.isoformat() if station.last_scored_at else None,
            }
            
        except Exception as e:
            print(f"FeedbackProcessor Error: {e}")
            db.rollback()
            raise

    @staticmethod
    def on_new_review_received(report_id: str, station_id: str, db: Session):
        """Backward-compatible wrapper used by older flows."""
        return FeedbackProcessor.process_feedback(report_id=report_id, station_id=station_id, db=db)
