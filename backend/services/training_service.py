import logging
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from backend.services.data_loader_service import DataLoaderService
from backend.services.preprocessor import ReviewPreprocessor
from backend.services.risk_score_ml_service import risk_score_ml_service

logger = logging.getLogger(__name__)


class TrainingService:
    """Incremental-update manager for the isolated hybrid ML pipeline."""

    @staticmethod
    def _models_dir() -> Path:
        return Path(__file__).resolve().parents[1] / "models"

    @staticmethod
    def _derive_label_from_review(review_row: Any) -> str:
        severity = int(getattr(review_row, "severity", 1) or 1)
        if severity >= 3:
            return "High"
        if severity == 2:
            return "Medium"
        return "Low"

    @staticmethod
    def _ensure_text_preprocessor(cleaned_texts: List[str]) -> Optional[Any]:
        if not cleaned_texts:
            return None

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            import joblib

            vectorizer = TfidfVectorizer(max_features=256, ngram_range=(1, 2))
            vectorizer.fit(cleaned_texts)
            joblib.dump(vectorizer, TrainingService._models_dir() / "feature_preprocessor.joblib")
            return vectorizer
        except Exception as exc:
            logger.warning("Could not refresh feature_preprocessor.joblib: %s", exc)
            return None

    @staticmethod
    def _build_training_matrix(db: Any, replay_reviews: List[Any]) -> tuple[np.ndarray, np.ndarray]:
        station_cache: Dict[Any, Any] = {}
        encoded_rows: List[np.ndarray] = []
        labels: List[str] = []

        from app.models import ChargingStation

        for review in replay_reviews:
            station = station_cache.get(review.station_id)
            if station is None:
                station = db.query(ChargingStation).filter(ChargingStation.id == review.station_id).first()
                if station is None:
                    continue
                station_cache[review.station_id] = station

            feature_payload = DataLoaderService.map_database_to_features(db, review, station)
            encoded_rows.append(risk_score_ml_service._encode_feature_row(feature_payload))
            labels.append(TrainingService._derive_label_from_review(review))

        if not encoded_rows:
            raise ValueError("No valid review rows were available to build a training minibatch.")

        X_raw = np.vstack(encoded_rows)
        y_batch = risk_score_ml_service.label_encoder.transform(labels)
        return X_raw, y_batch

    @staticmethod
    def _save_boosting_artifacts(model: Any) -> None:
        models_dir = TrainingService._models_dir()
        pkl_path = models_dir / "hybrid_model_gb.pkl"
        json_path = models_dir / "xgb_risk_classifier.json"

        with open(pkl_path, "wb") as handle:
            pickle.dump(model, handle)

        if hasattr(model, "save_model"):
            model.save_model(str(json_path))

    @staticmethod
    def trigger_incremental_update(
        new_review_data: Dict[str, Any],
        new_review_label: Optional[str],
        db: Any,
        num_samples: int = 100,
    ) -> Dict[str, Any]:
        """
        Perform a fast minibatch refresh around the newest review and save updated artifacts.
        """
        if not risk_score_ml_service.initialized:
            raise RuntimeError(
                f"Hybrid ML engine is not initialized. Reason: {risk_score_ml_service.initialization_error or 'unknown'}"
            )

        replay_reviews = DataLoaderService.get_recent_reviews(db, num_samples=num_samples)
        if not replay_reviews:
            return {"updated": False, "reason": "No recent reviews available."}

        cleaned_texts = ReviewPreprocessor.batch_clean(
            [
                new_review_data.get("review_text", ""),
                *[(getattr(review, "description", "") or "") for review in replay_reviews],
            ]
        )
        TrainingService._ensure_text_preprocessor(cleaned_texts)

        X_raw, y_batch = TrainingService._build_training_matrix(db, replay_reviews)
        X_scaled = risk_score_ml_service.scaler.transform(X_raw)
        X_deep = risk_score_ml_service.cnn_extractor.predict(
            X_scaled.reshape(-1, X_scaled.shape[1], 1),
            verbose=0,
        )
        X_hybrid = np.hstack([X_scaled, X_deep])

        model = risk_score_ml_service.gb_model
        if hasattr(model, "fit"):
            model.fit(X_hybrid, y_batch)
        else:
            raise RuntimeError("Loaded boosting model does not support fit().")

        TrainingService._save_boosting_artifacts(model)
        risk_score_ml_service._load_artifacts()

        return {
            "updated": True,
            "samples": int(len(y_batch)),
            "label_used": new_review_label or "derived_from_severity",
            "artifact": str(TrainingService._models_dir() / "hybrid_model_gb.pkl"),
        }
