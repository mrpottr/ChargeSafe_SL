from sqlalchemy.orm import Session
from app.services.data_loader_service import DataLoaderService
from app.services.risk_score_ml_service import ML_LIBS_AVAILABLE, risk_scorer

import numpy as np


class TrainingService:
    # Incremental training is kept behind this service so the feedback pipeline
    # can request model refreshes without owning ML artifact details itself.
    @staticmethod
    def trigger_incremental_update(station_id: str, db: Session):
        """
        Incrementally updates the XGBoost model with the latest data buffer.
        If ML libraries are missing, it is a no-op protecting the backend stream.
        """
        if not ML_LIBS_AVAILABLE or not risk_scorer.initialized:
            print("ML Training Simulation: Artifacts or libraries not present. Skipping update.")
            return
            
        print(f"Triggering incremental training update for station {station_id}...")
        
        # Recent reports act as a small replay buffer so each update sees fresh
        # user feedback instead of only the single newest report.
        recent_reports = DataLoaderService.get_recent_reviews(db, num_samples=20)
        if not recent_reports:
            return
        
        # The mini-batch is assembled in memory to keep the incremental update
        # compact and avoid repeated database lookups for the same station.
        from app.models import ChargingStation
        # A local station cache keeps this loop from turning into an N+1 query pattern.
        station_cache = {}
        X_batch_raw = []
        
        for report in recent_reports:
            if report.station_id not in station_cache:
                station = db.query(ChargingStation).filter(ChargingStation.id == report.station_id).first()
                if not station:
                    continue
                station_cache[report.station_id] = station
            
            st = station_cache[report.station_id]
            features_dict = DataLoaderService.map_database_to_features(db, report, st)
            
            row = []
            for f in risk_scorer.feature_names:
                val = features_dict.get(f, 0)
                if f in risk_scorer.le_dict:
                    le = risk_scorer.le_dict[f]
                    val_str = str(val)
                    if val_str in le.classes_:
                        row.append(int(le.transform([val_str])[0]))
                    elif 'Unknown' in le.classes_:
                        row.append(int(le.transform(['Unknown'])[0]))
                    else:
                        row.append(0)
                else:
                    row.append(val)
            X_batch_raw.append(row)
            
        if not X_batch_raw:
            return
            
        X_batch_raw = np.array(X_batch_raw, dtype=float)
        
        # Feature extraction mirrors the offline training pipeline so the booster
        # continues to receive the same hybrid representation shape.
        X_sc = risk_scorer.scaler.transform(X_batch_raw)
        X_deep = risk_scorer.cnn_extractor.predict(X_sc.reshape(-1, X_sc.shape[1], 1), verbose=0)
        X_hyb = np.hstack([X_sc, X_deep])
        
        # Labels are approximated from severity here to keep the online update
        # path simple until a richer analyst-reviewed labeling flow exists.
        def get_label(rep):
            if rep.severity >= 3: return "High"
            if rep.severity == 2: return "Medium"
            return "Low"
            
        y_labels = [get_label(r) for r in recent_reports if r.station_id in station_cache]
        y_batch = risk_scorer.label_encoder.transform(y_labels)
        
        # The final step updates the underlying booster in place and writes the
        # refreshed artifact back to disk for later scoring calls.
        try:
            # The wrapper exposes the raw booster, which is what XGBoost expects
            # for a lightweight incremental update round.
            booster = risk_scorer.xgb_model.get_booster()
            
            import xgboost as xgb
            dmat = xgb.DMatrix(X_hyb, label=y_batch)
            
            # A single boosting round keeps the update cheap enough to run as a
            # background maintenance action.
            print("Running XGBoost incremental partial fit...")
            booster.update(dmat, booster.best_iteration or 0)
            
            # Persisting the refreshed model immediately keeps future scoring and
            # later training steps pointed at the same artifact version.
            model_path = risk_scorer.models_dir + "/xgb_risk_classifier.json"
            risk_scorer.xgb_model.save_model(model_path)
            
            print("Successfully updated XGBoost model artifacts incrementally.")
        except Exception as e:
            print(f"Error during incremental update: {e}")
