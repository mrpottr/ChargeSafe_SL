from datetime import datetime

from sqlalchemy.orm import Session

from app.models import ChargingStation, Report, ScoreHistory
from app.services.data_loader_service import DataLoaderService
from app.services.risk_score_ml_service import risk_scorer

class FeedbackProcessor:
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
            
            # STEP 1 & 2: Calculate New Score & Update Database
            features_dict = DataLoaderService.map_database_to_features(db, station, report)
            new_risk_score = risk_scorer.calculate_latest_risk_score(features_dict)
            
            # Update the station record immediately for real-time UI refreshes.
            station.safety_score = new_risk_score
            station.last_scored_at = datetime.utcnow()
            
            # Determine Risk Level equivalent from 0-100 score logic natively
            if new_risk_score <= 30: new_risk_level = "LOW"
            elif new_risk_score <= 70: new_risk_level = "MEDIUM"
            else: new_risk_level = "HIGH"
            
            # Record it in history for graph visualization natively provided by app
            import uuid
            score_history = ScoreHistory(
                id=uuid.uuid4(),
                station_id=station.id,
                score=new_risk_score,
                level=new_risk_level,
                trigger="Auto(ML)"
            )
            db.add(score_history)
            
            # Optionally sync Cyber Risk level to the overall prediction to reflect it in the UI mapping.
            station.cyber_risk_level = new_risk_level
            
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
