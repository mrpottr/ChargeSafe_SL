import json
import logging
import os
import pickle
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
except ImportError:  # pragma: no cover
    xgb = None

try:
    from tensorflow import keras
except ImportError:  # pragma: no cover
    keras = None


ML_LIBS_AVAILABLE = xgb is not None and keras is not None


class RiskScoreMLService:
    # This function initializes the RiskScoreMLService by setting up necessary paths and placeholders for machine learning models. 
    # It is built to automatically detect if the required machine learning dependencies (XGBoost, TensorFlow) are available, 
    # and safely attempts to load the pre-trained artifacts if possible.
    def __init__(self):
        self.models_dir = os.path.join(os.path.dirname(__file__), "..", "..", "models")
        self.initialized = False
        self.initialization_error: Optional[str] = None

        self.xgb_model = None
        self.cnn_extractor = None
        self.scaler = None
        self.le_dict = None
        self.label_encoder = None
        self.feature_names: List[str] = []

        if ML_LIBS_AVAILABLE:
            self._load_artifacts()
        else:
            missing = []
            if xgb is None:
                missing.append("xgboost")
            if keras is None:
                missing.append("tensorflow")
            self.initialization_error = f"Missing ML dependencies: {', '.join(missing)}"
            logger.warning(self.initialization_error)

    # This function loads the trained machine learning models, scalers, and encoders from the filesystem into memory. 
    # It is built using standard Python deserialization (pickle and json) alongside TensorFlow and XGBoost loading mechanisms, 
    # ensuring the prediction engine is fully prepared to calculate risk scores.
    def _load_artifacts(self):
        try:
            self.xgb_model = xgb.XGBClassifier()
            self.xgb_model.load_model(os.path.join(self.models_dir, "xgb_risk_classifier.json"))

            self.cnn_extractor = keras.models.load_model(
                os.path.join(self.models_dir, "cnn_extractor.keras")
            )

            with open(os.path.join(self.models_dir, "scaler.pkl"), "rb") as scaler_file:
                self.scaler = pickle.load(scaler_file)
            with open(os.path.join(self.models_dir, "le_dict.pkl"), "rb") as encoder_file:
                self.le_dict = pickle.load(encoder_file)
            with open(os.path.join(self.models_dir, "label_encoder.pkl"), "rb") as label_file:
                self.label_encoder = pickle.load(label_file)
            with open(os.path.join(self.models_dir, "feature_names.json"), "r", encoding="utf-8") as features_file:
                self.feature_names = json.load(features_file)

            self.initialized = True
            self.initialization_error = None
            logger.info("Hybrid ML artifacts loaded successfully from %s", self.models_dir)
        except Exception as exc:
            self.initialized = False
            self.initialization_error = str(exc)
            logger.exception("Failed to load hybrid ML artifacts: %s", exc)

    # This function calculates a comprehensive risk score for a charging station based on its raw data attributes and feedback. 
    # It is built by transforming the raw data using loaded scalers, passing it through a hybrid CNN-XGBoost pipeline, 
    # and adjusting the final score based on recent user feedback signals.
    def calculate_latest_risk_score(self, raw_feature_dict: Dict[str, Any]) -> float:
        if not self.initialized:
            raise RuntimeError(
                f"Hybrid ML engine is not initialized. Reason: {self.initialization_error or 'unknown'}"
            )

        row = {feature: raw_feature_dict.get(feature, 0) for feature in self.feature_names}

        for column, encoder in self.le_dict.items():
            raw_value = str(row.get(column, "Unknown"))
            if hasattr(encoder, "classes_") and raw_value in encoder.classes_:
                row[column] = int(encoder.transform([raw_value])[0])
            elif hasattr(encoder, "classes_") and "Unknown" in encoder.classes_:
                row[column] = int(encoder.transform(["Unknown"])[0])
            else:
                row[column] = 0

        X_raw = np.array([[row[feature] for feature in self.feature_names]], dtype=float)
        X_scaled = self.scaler.transform(X_raw)
        X_deep = self.cnn_extractor.predict(X_scaled.reshape(1, X_scaled.shape[1], 1), verbose=0)
        X_hybrid = np.hstack([X_scaled, X_deep])
        pred_proba = self.xgb_model.predict_proba(X_hybrid)[0]

        class_scores = {"Low": 20.0, "Medium": 57.0, "High": 88.0}
        risk_score = 0.0
        for index, probability in enumerate(pred_proba):
            label = self.label_encoder.classes_[index]
            risk_score += probability * class_scores.get(label, 50.0)

        review_modifier = float(raw_feature_dict.get("review_risk_modifier", 0.0))
        feedback_signal_score = float(raw_feature_dict.get("feedback_signal_score", 0.0))
        # Positive feedback nudges risk down or keeps it steady, negative feedback nudges it up.
        feedback_signal_adjustment = feedback_signal_score * 12.0
        risk_score = float(np.clip(risk_score + review_modifier * 0.5 + feedback_signal_adjustment, 0.0, 100.0))
        return round(risk_score, 1)

    # This function translates a numerical risk score into a visual hex color code for frontend display. 
    # It is built using simple threshold comparisons to return green for low risk, yellow for medium risk, 
    # and red for high risk scenarios.
    @staticmethod
    def get_color_from_risk_score(risk_score: float) -> str:
        if risk_score < 30:
            return "#2ecc71"
        if risk_score <= 70:
            return "#f1c40f"
        return "#e74c3c"

    # This function categorizes a numerical risk score into a human-readable text label. 
    # It is built similarly to the color mapper, using predefined score boundaries to classify 
    # the station as 'Low Risk', 'Medium Risk', or 'High Risk'.
    @staticmethod
    def get_risk_level_from_score(risk_score: float) -> str:
        if risk_score < 30:
            return "Low Risk"
        if risk_score <= 70:
            return "Medium Risk"
        return "High Risk"

    # This function takes an individual charging station's data dictionary and adds calculated visual properties. 
    # It is built by safely extracting the station's risk score and appending the corresponding 
    # color hex code and risk level string directly into the dictionary.
    @staticmethod
    def enrich_station_with_color(station_dict: Dict[str, Any]) -> Dict[str, Any]:
        risk_score = station_dict.get("risk_score", 50.0)
        if risk_score is None:
            risk_score = 50.0

        try:
            risk_score = float(risk_score)
        except (TypeError, ValueError):
            risk_score = 50.0

        enriched = station_dict.copy()
        enriched["color"] = RiskScoreMLService.get_color_from_risk_score(risk_score)
        enriched["risk_level"] = RiskScoreMLService.get_risk_level_from_score(risk_score)
        return enriched

    # This function processes a complete list of charging station dictionaries, adding visual properties to each one. 
    # It is built using a Python list comprehension that applies the single-station enrichment logic 
    # iteratively across the entire dataset.
    @staticmethod
    def enrich_stations_with_colors(stations_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [RiskScoreMLService.enrich_station_with_color(station) for station in stations_list]


risk_scorer = RiskScoreMLService()
