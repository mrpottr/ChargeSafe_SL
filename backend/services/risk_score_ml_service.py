import json
import logging
import os
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
except ImportError:  # pragma: no cover - optional dependency at runtime
    xgb = None

try:
    from tensorflow import keras
except ImportError:  # pragma: no cover - optional dependency at runtime
    keras = None


class RiskScoreMLService:
    """Hybrid ML risk scorer backed by the artifacts stored in backend/models."""

    LOW_RISK_MAX = 30.0
    MEDIUM_RISK_MAX = 70.0

    def __init__(self, models_dir: Optional[Path] = None) -> None:
        self.models_dir = Path(models_dir or Path(__file__).resolve().parents[1] / "models")
        self.initialized = False
        self.initialization_error: Optional[str] = None

        self.xgb_model = None
        self.gb_model = None
        self.cnn_extractor = None
        self.scaler = None
        self.label_encoders: Dict[str, Any] = {}
        self.label_encoder = None
        self.feature_names: List[str] = []
        self.feature_preprocessor = None

        self._load_artifacts()

    def _load_pickle_if_present(self, path: Path) -> Any:
        if not path.exists():
            return None
        with open(path, "rb") as handle:
            return pickle.load(handle)

    def _load_artifacts(self) -> None:
        """Load every artifact required by the hybrid CNN + XGBoost pipeline."""
        if xgb is None:
            self.initialization_error = "xgboost is not installed."
            logger.warning(self.initialization_error)
            return

        if keras is None:
            self.initialization_error = "tensorflow is not installed."
            logger.warning(self.initialization_error)
            return

        try:
            gb_pickle_path = self.models_dir / "hybrid_model_gb.pkl"
            xgb_json_path = self.models_dir / "xgb_risk_classifier.json"
            if gb_pickle_path.exists():
                self.gb_model = self._load_pickle_if_present(gb_pickle_path)
            if xgb_json_path.exists():
                self.xgb_model = xgb.XGBClassifier()
                self.xgb_model.load_model(str(xgb_json_path))
                if self.gb_model is None:
                    self.gb_model = self.xgb_model

            self.cnn_extractor = keras.models.load_model(self.models_dir / "cnn_extractor.keras")

            feature_preprocessor_path = self.models_dir / "feature_preprocessor.joblib"
            if feature_preprocessor_path.exists():
                try:
                    import joblib

                    self.feature_preprocessor = joblib.load(feature_preprocessor_path)
                except Exception as exc:
                    logger.warning("Could not load feature_preprocessor.joblib: %s", exc)

            with open(self.models_dir / "scaler.pkl", "rb") as scaler_file:
                self.scaler = pickle.load(scaler_file)
            with open(self.models_dir / "le_dict.pkl", "rb") as encoder_file:
                self.label_encoders = pickle.load(encoder_file)

            label_encoder_pickle = self.models_dir / "label_encoder.pkl"
            label_encoder_joblib = self.models_dir / "label_encoder.joblib"
            if label_encoder_joblib.exists():
                import joblib

                self.label_encoder = joblib.load(label_encoder_joblib)
            elif label_encoder_pickle.exists():
                with open(label_encoder_pickle, "rb") as class_file:
                    self.label_encoder = pickle.load(class_file)
            with open(self.models_dir / "feature_names.json", "r", encoding="utf-8") as feature_file:
                self.feature_names = json.load(feature_file)

            if self.gb_model is None:
                raise FileNotFoundError("No gradient boosting artifact found in backend/models.")

            self.initialized = True
            self.initialization_error = None
            logger.info("Hybrid ML artifacts loaded from %s", self.models_dir)
        except Exception as exc:  # pragma: no cover - depends on local ML runtime
            self.initialization_error = str(exc)
            self.initialized = False
            logger.exception("Failed to load hybrid ML artifacts: %s", exc)

    def preprocess_review_text(self, review_text: str) -> str:
        normalized = " ".join((review_text or "").strip().split())
        return normalized or "no_review_text"

    def _encode_feature_row(self, raw_feature_dict: Dict[str, Any]) -> np.ndarray:
        prepared_row = {feature: raw_feature_dict.get(feature, 0) for feature in self.feature_names}

        for feature_name, encoder in self.label_encoders.items():
            raw_value = str(prepared_row.get(feature_name, "Unknown"))
            if hasattr(encoder, "classes_") and raw_value in encoder.classes_:
                prepared_row[feature_name] = int(encoder.transform([raw_value])[0])
                continue

            if hasattr(encoder, "classes_") and "Unknown" in encoder.classes_:
                prepared_row[feature_name] = int(encoder.transform(["Unknown"])[0])
            else:
                prepared_row[feature_name] = 0

        return np.array(
            [[prepared_row[feature] for feature in self.feature_names]],
            dtype=float,
        )

    def _predict_from_feature_row(self, feature_vector: np.ndarray, review_modifier: float = 0.01) -> float:
        scaled_vector = self.scaler.transform(feature_vector)
        cnn_features = self.cnn_extractor.predict(
            scaled_vector.reshape(1, scaled_vector.shape[1], 1),
            verbose=0,
        )
        hybrid_vector = np.hstack([scaled_vector, cnn_features])

        if hasattr(self.gb_model, "predict_proba"):
            class_probabilities = self.gb_model.predict_proba(hybrid_vector)[0]
        elif self.xgb_model is not None:
            class_probabilities = self.xgb_model.predict_proba(hybrid_vector)[0]
        else:
            raise RuntimeError("No probability-capable hybrid model is loaded.")

        class_scores = {"Low": 20.0, "Medium": 57.0, "High": 88.0}
        risk_score = 0.0
        for index, probability in enumerate(class_probabilities):
            label = self.label_encoder.classes_[index]
            risk_score += probability * class_scores.get(label, 50.0)

        adjusted_score = float(np.clip(risk_score + (review_modifier * 0.5), 0.0, 100.0))
        return round(adjusted_score, 1)

    def calculate_latest_risk_score(self, raw_feature_dict: Dict[str, Any]) -> float:
        """
        Calculate a 0-100 risk score using the shipped hybrid pipeline.

        If the required ML stack is unavailable, this raises instead of silently
        producing a mock score so callers can detect that the real model is not active.
        """
        if not self.initialized:
            raise RuntimeError(
                f"Hybrid ML engine is not initialized. Reason: {self.initialization_error or 'unknown'}"
            )

        feature_vector = self._encode_feature_row(raw_feature_dict)
        review_modifier = float(raw_feature_dict.get("review_risk_modifier", 0.0))
        return self._predict_from_feature_row(feature_vector, review_modifier=review_modifier)

    def calculate_latest_risk_score_from_review(
        self,
        review_text: str,
        raw_feature_dict: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Review-text entry point that keeps compatibility with the spec while still
        relying on the shipped tabular hybrid artifact space.
        """
        feature_payload = dict(raw_feature_dict or {})
        cleaned_text = self.preprocess_review_text(review_text)

        if self.feature_preprocessor is not None:
            try:
                transformed = self.feature_preprocessor.transform([cleaned_text])
                feature_payload["avg_keyword_count"] = float(getattr(transformed, "nnz", 0))
            except Exception:
                logger.debug("feature_preprocessor.joblib could not transform review text.", exc_info=True)

        if "avg_keyword_count" not in feature_payload:
            feature_payload["avg_keyword_count"] = float(len(cleaned_text.split()))

        feature_payload.setdefault("review_risk_modifier", 0.01)
        feature_payload.setdefault("station", "Unknown Station")
        feature_payload.setdefault("Manufacturer", "Unknown")
        feature_payload.setdefault("PlugType", "Unknown")
        feature_payload.setdefault("Component", "Unknown")
        feature_payload.setdefault("vehicle_model", "Unknown")
        feature_payload.setdefault("EV Level2 EVSE Num", 1)
        feature_payload.setdefault("RapidCharge", 0)
        feature_payload.setdefault("FastCharge", 0)
        feature_payload.setdefault("max_charge_power", 7.0)
        feature_payload.setdefault("kWhDelivered", 20.0)
        feature_payload.setdefault("chargingDuration", 2.0)
        feature_payload.setdefault("avg_rating", 3.0)
        feature_payload.setdefault("review_count", 1)
        feature_payload.setdefault("bad_review_ratio", 0.0)
        return self.calculate_latest_risk_score(feature_payload)

    @staticmethod
    def map_probability_to_continuous_risk(probability: float) -> float:
        """
        Spec compatibility helper for callers expecting a 0.01 to 2.0 scale.
        """
        return float(np.clip(probability * 2.0, 0.01, 2.0))

    @classmethod
    def get_risk_status(cls, risk_score: float) -> str:
        if risk_score < cls.LOW_RISK_MAX:
            return "Low Risk"
        if risk_score <= cls.MEDIUM_RISK_MAX:
            return "Medium Risk"
        return "High Risk"

    @classmethod
    def get_color(cls, risk_score: float) -> str:
        if risk_score < cls.LOW_RISK_MAX:
            return "Green"
        if risk_score <= cls.MEDIUM_RISK_MAX:
            return "Yellow"
        return "Red"

    @classmethod
    def get_hex_color(cls, risk_score: float) -> str:
        if risk_score < cls.LOW_RISK_MAX:
            return "#2ecc71"
        if risk_score <= cls.MEDIUM_RISK_MAX:
            return "#f1c40f"
        return "#e74c3c"

    @classmethod
    def build_visualization_payload(cls, station_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Append the frontend-facing color fields without changing the original map stack.
        """
        enriched_payload = dict(station_payload)
        risk_score = float(enriched_payload.get("risk_score") or 0.0)
        enriched_payload["risk_status"] = cls.get_risk_status(risk_score)
        enriched_payload["color"] = cls.get_color(risk_score)
        enriched_payload["color_hex"] = cls.get_hex_color(risk_score)
        return enriched_payload

    @classmethod
    def build_visualization_payloads(cls, stations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [cls.build_visualization_payload(station) for station in stations]

    @staticmethod
    def assign_station_risk_fields(station: Any, risk_score: float) -> None:
        """
        Populate existing ORM fields only; no schema changes are introduced.
        """
        station.safety_score = risk_score
        station.last_scored_at = datetime.utcnow()

        risk_level = RiskScoreMLService.get_risk_status(risk_score)
        if hasattr(station, "cyber_risk_level"):
            try:
                from app.models import CyberRiskLevel

                if risk_level == "Low Risk":
                    station.cyber_risk_level = CyberRiskLevel.low
                elif risk_level == "Medium Risk":
                    station.cyber_risk_level = CyberRiskLevel.medium
                else:
                    station.cyber_risk_level = CyberRiskLevel.high
            except Exception:
                logger.debug("CyberRiskLevel enum could not be applied.", exc_info=True)


risk_score_ml_service = RiskScoreMLService()
