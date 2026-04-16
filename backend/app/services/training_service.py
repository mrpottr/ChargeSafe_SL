from sqlalchemy.orm import Session
from app.services.data_loader_service import DataLoaderService
from app.services.risk_score_ml_service import ML_LIBS_AVAILABLE, risk_scorer

import numpy as np

class TrainingService:
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
        
        # 1. Fetch recent reviews for incremental experience replay
        recent_reports = DataLoaderService.get_recent_reviews(db, num_samples=20)
        if not recent_reports:
            return
        
        # 2. Build Mini-Batch Dataset
        from app.models import ChargingStation
        # Cache stations to avoid N+1 querying in this minibatch loop
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
        
        # 3. Feature Extraction (Scale + CNN)
        X_sc = risk_scorer.scaler.transform(X_batch_raw)
        X_deep = risk_scorer.cnn_extractor.predict(X_sc.reshape(-1, X_sc.shape[1], 1), verbose=0)
        X_hyb = np.hstack([X_sc, X_deep])
        
        # 4. Generate 'Labels' for incremental update based on severity 
        # (In real scenario, labels are assigned by analysts or severity maps)
        # Assuming Severity >= 3 is 'High', == 2 is 'Medium', <= 1 is 'Low'
        def get_label(rep):
            if rep.severity >= 3: return "High"
            if rep.severity == 2: return "Medium"
            return "Low"
            
        y_labels = [get_label(r) for r in recent_reports if r.station_id in station_cache]
        y_batch = risk_scorer.label_encoder.transform(y_labels)
        
        # 5. Continuous Online Update (XGBoost incremental fit)
        try:
            # xgb_model refers to XGBClassifier wrapper interface. 
            # We access the internal Booster to update.
            booster = risk_scorer.xgb_model.get_booster()
            
            import xgboost as xgb
            dmat = xgb.DMatrix(X_hyb, label=y_batch)
            
            # Perform single round of boosting update
            print("Running XGBoost incremental partial fit...")
            booster.update(dmat, booster.best_iteration or 0)
            
            # Save updated artifact back
            model_path = risk_scorer.models_dir + "/xgb_risk_classifier.json"
            risk_scorer.xgb_model.save_model(model_path)
            
            print("Successfully updated XGBoost model artifacts incrementally.")
        except Exception as e:
            print(f"Error during incremental update: {e}")
