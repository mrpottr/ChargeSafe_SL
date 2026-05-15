from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from app.bootstrap import REMOVED_STATION_NAMES, SEED_STATIONS, seed_initial_data
from app.models import (
    ChargingStation,
    CyberCriterion,
    CyberRiskLevel,
    CyberScore,
    Report,
    ScoreHistory,
    StationStatus,
    TemperatureHistory,
    User,
)
from app.services.cyber_scoring_service import CyberScoringService
from app.services.data_loader_service import DataLoaderService
from app.services.training_service import TrainingService


def test_seed_initial_data_creates_demo_stations_history_and_admin(db_session, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin_password_123")

    seed_initial_data(db_session)

    stations = db_session.query(ChargingStation).all()
    admin = db_session.query(User).filter(User.username == "admin").first()
    score_history_count = db_session.query(ScoreHistory).count()
    temperature_history_count = db_session.query(TemperatureHistory).count()

    assert len(stations) == len(SEED_STATIONS)
    assert admin is not None
    assert admin.email == "admin@chargesafe.app"
    assert score_history_count == len(SEED_STATIONS) * 4
    assert temperature_history_count == len(SEED_STATIONS) * 4


def test_seed_initial_data_removes_stale_station_and_updates_legacy_admin_email(db_session, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin_password_123")
    stale_station = ChargingStation(
        name=next(iter(REMOVED_STATION_NAMES)),
        latitude=6.1,
        longitude=79.9,
        status=StationStatus.unknown,
    )
    legacy_admin = User(
        username="admin",
        email="admin@chargesafe.local",
        password_hash="hashed",
        role="admin",
        email_verified=True,
    )
    db_session.add(stale_station)
    db_session.add(legacy_admin)
    db_session.commit()

    seed_initial_data(db_session)

    assert db_session.query(ChargingStation).filter(ChargingStation.name == stale_station.name).first() is None
    refreshed_admin = db_session.query(User).filter(User.username == "admin").first()
    assert refreshed_admin.email == "admin@chargesafe.app"


def test_seed_initial_data_requires_admin_password_for_missing_admin(db_session, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    with pytest.raises(RuntimeError):
        seed_initial_data(db_session)


def test_data_loader_feedback_analysis_and_station_summary(db_session, station_factory, user_factory, report_factory):
    station = station_factory()
    user = user_factory()
    report_factory(
        user_id=user.id,
        station_id=station.id,
        severity=5,
        description="The charger was overheating and offline with sparks.",
    )
    report_factory(
        user_id=user.id,
        station_id=station.id,
        severity=1,
        description="Station working fine and charging successfully.",
        report_type="positive",
    )

    negative_signal = DataLoaderService.analyze_feedback_signal(
        "The charger was overheating and offline with sparks.",
        severity=5,
    )
    positive_signal = DataLoaderService.analyze_feedback_signal(
        "Station working fine and charging successfully.",
        severity=1,
        report_type="positive",
    )
    summary = DataLoaderService.get_station_summary(db_session, station.id)
    newest = DataLoaderService.get_newest_review(db_session, station.id)

    assert negative_signal["label"] == "negative"
    assert positive_signal["label"] == "positive"
    assert summary["review_count"] == 2
    assert summary["bad_review_ratio"] == 0.5
    assert newest is not None
    assert "working fine" in newest.description.lower()


def test_map_database_to_features_builds_ml_payload(db_session, station_factory, user_factory, report_factory):
    station = station_factory(
        charging_power_kw=120,
        operator="ChargeSafe",
        connector_types="CCS2",
        risk_score=84,
    )
    user = user_factory()
    report = report_factory(
        user_id=user.id,
        station_id=station.id,
        severity=4,
        description="Overheating and unstable charging session with smoke warnings.",
    )

    payload = DataLoaderService.map_database_to_features(db_session, station, report)

    assert payload["max_charge_power"] == 120
    assert payload["RapidCharge"] == 1
    assert payload["FastCharge"] == 1
    assert payload["Manufacturer"] == "ChargeSafe"
    assert payload["PlugType"] == "CCS2"
    assert payload["review_count"] >= 1
    assert payload["feedback_signal_label"] == "negative"


def test_fetch_openchargemap_normalizes_results_and_skips_missing_coordinates(monkeypatch):
    sample_payload = [
        {
            "ID": 101,
            "AddressInfo": {
                "Title": "Colombo Central",
                "Latitude": 6.9,
                "Longitude": 79.8,
                "AddressLine1": "Address 1",
                "Town": "Colombo",
            },
            "OperatorInfo": {"Title": "Operator A"},
            "Connections": [
                {"ConnectionType": {"Title": "CCS2"}, "PowerKW": 50},
                {"ConnectionType": {"Title": "Type 2"}, "PowerKW": 22},
            ],
        },
        {
            "ID": 202,
            "AddressInfo": {"Title": "Broken Station"},
        },
    ]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return sample_payload

    monkeypatch.setattr("app.services.data_loader_service.requests.get", lambda *args, **kwargs: FakeResponse())

    stations = DataLoaderService.fetch_openchargemap_for_sri_lanka()

    assert len(stations) == 1
    assert stations[0]["name"] == "Colombo Central"
    assert stations[0]["connector_types"] == "CCS2, Type 2"
    assert stations[0]["charging_power_kw"] == 50
    assert stations[0]["status"] == "operational"


def test_fetch_openchargemap_rejects_placeholder_key(monkeypatch):
    monkeypatch.setattr("app.services.data_loader_service.OPENCHARGEMAP_API_KEY", "PASTE_YOUR_API_KEY_HERE")

    with pytest.raises(RuntimeError):
        DataLoaderService.fetch_openchargemap_for_sri_lanka()


def test_upsert_apply_payload_and_sync_openchargemap(db_session, monkeypatch):
    station_data = {
        "ocm_id": 1,
        "name": "Synced Station",
        "latitude": 7.0,
        "longitude": 80.0,
        "address": "Sync address",
        "city": "Kandy",
        "operator": "Sync Operator",
        "connector_types": "CCS2",
        "charging_power_kw": 60.0,
        "status": "operational",
    }

    station, created, updated = DataLoaderService._upsert_station(db_session, station_data, force_update=False)
    assert created is True
    assert updated is False

    station_data_updated = {**station_data, "name": "Synced Station 2", "charging_power_kw": 90.0}
    station, created, updated = DataLoaderService._upsert_station(db_session, station_data_updated, force_update=False)
    assert created is False
    assert updated is True

    risk_level = DataLoaderService._apply_risk_score(station, 88.0)
    payload = DataLoaderService.build_station_payload(station)
    assert risk_level == "HIGH"
    assert payload["color"] == "#e74c3c"
    assert payload["risk_level"] == "High Risk"

    monkeypatch.setattr(
        DataLoaderService,
        "fetch_openchargemap_for_sri_lanka",
        staticmethod(lambda: [station_data_updated, {**station_data, "ocm_id": 2, "latitude": 8.0, "longitude": 81.0}]),
    )
    monkeypatch.setattr(
        "app.services.data_loader_service.risk_scorer.calculate_latest_risk_score",
        lambda features: 67.5,
    )

    stats = DataLoaderService.sync_openchargemap_to_database(db_session, force_update=True)

    assert stats["fetched"] == 2
    assert stats["created"] >= 1
    assert stats["updated"] >= 1
    assert stats["scored"] == 2
    assert stats["failed"] == 0
    assert len(stats["stations"]) == 2


def test_sync_openchargemap_handles_station_failure_and_global_failure(db_session, monkeypatch):
    monkeypatch.setattr(
        DataLoaderService,
        "fetch_openchargemap_for_sri_lanka",
        staticmethod(lambda: [{"ocm_id": 1, "name": "Bad"}]),
    )
    monkeypatch.setattr(
        DataLoaderService,
        "_upsert_station",
        staticmethod(lambda db, station_data, force_update: (_ for _ in ()).throw(RuntimeError("boom"))),
    )

    stats = DataLoaderService.sync_openchargemap_to_database(db_session, force_update=False)
    assert stats["failed"] == 1
    assert stats["stations"] == []

    monkeypatch.setattr(
        DataLoaderService,
        "fetch_openchargemap_for_sri_lanka",
        staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("network down"))),
    )
    failed_stats = DataLoaderService.sync_openchargemap_to_database(db_session, force_update=False)
    assert failed_stats["error"] == "network down"


def test_cyber_scoring_service_scores_station_and_all_stations(db_session, station_factory):
    station = station_factory(
        risk_score=88.0,
        status=StationStatus.faulty,
        fault_count=5,
        temperature_celsius=52.0,
    )
    station.firmware_age_days = 365
    station.power_status = "Unstable"
    db_session.commit()

    criteria = [
        CyberCriterion(criterion_name="Secure Firmware Update Mechanism", weight=1.0, score_medium=2, score_high=4),
        CyberCriterion(criterion_name="Physical Tamper Protection", weight=1.0, score_medium=2, score_high=4),
        CyberCriterion(criterion_name="Personal Data Privacy Controls", weight=1.0, score_medium=2, score_high=4),
        CyberCriterion(criterion_name="Other Generic Criterion", weight=1.0, score_medium=2, score_high=4),
    ]
    db_session.add_all(criteria)
    db_session.commit()

    assert CyberScoringService._base_score(station) == 4
    firmware_score, firmware_note = CyberScoringService._criterion_score(station, criteria[0])
    privacy_score, privacy_note = CyberScoringService._criterion_score(station, criteria[2])
    generic_score, _ = CyberScoringService._criterion_score(station, criteria[3])

    assert firmware_score == 4
    assert "Firmware age" in firmware_note
    assert privacy_score == 4
    assert "temperature" in privacy_note.lower()
    assert generic_score == 4
    assert CyberScoringService._score_to_risk_level(4, criteria[0]) == CyberRiskLevel.high

    created_rows = CyberScoringService.score_station(db_session, station)
    db_session.commit()
    db_session.refresh(station)
    assert created_rows == 4
    assert station.cyber_risk_level == CyberRiskLevel.high
    assert db_session.query(CyberScore).filter(CyberScore.station_id == station.id).count() == 4

    stats = CyberScoringService.score_all_stations(db_session)
    assert stats["stations_scored"] >= 1
    assert stats["score_rows_created"] >= 4


def test_cyber_scoring_returns_zero_when_no_criteria_exist(db_session, station_factory):
    station = station_factory()
    created_rows = CyberScoringService.score_station(db_session, station)
    assert created_rows == 0


def test_training_service_noops_without_ml_and_with_empty_reviews(monkeypatch):
    monkeypatch.setattr("app.services.training_service.ML_LIBS_AVAILABLE", False)
    TrainingService.trigger_incremental_update("station-1", db=None)

    monkeypatch.setattr("app.services.training_service.ML_LIBS_AVAILABLE", True)
    monkeypatch.setattr("app.services.training_service.risk_scorer", SimpleNamespace(initialized=False))
    TrainingService.trigger_incremental_update("station-1", db=None)

    fake_scorer = SimpleNamespace(initialized=True)
    monkeypatch.setattr("app.services.training_service.risk_scorer", fake_scorer)
    monkeypatch.setattr(
        "app.services.training_service.DataLoaderService.get_recent_reviews",
        lambda db, num_samples=20: [],
        raising=False,
    )
    TrainingService.trigger_incremental_update("station-1", db=None)


def test_training_service_updates_booster_when_recent_reviews_exist(monkeypatch):
    class FakeLabelEncoder:
        def transform(self, labels):
            return np.array([2 if label == "High" else 1 for label in labels])

    class FakeScaler:
        def transform(self, values):
            return np.array(values, dtype=float)

    class FakeCnnExtractor:
        def predict(self, values, verbose=0):
            return np.ones((values.shape[0], 1))

    class FakeBooster:
        def __init__(self):
            self.updated = False
            self.best_iteration = 0

        def update(self, dmat, iteration):
            self.updated = True

    class FakeXgbModel:
        def __init__(self, booster):
            self._booster = booster
            self.saved_model_path = None

        def get_booster(self):
            return self._booster

        def save_model(self, path):
            self.saved_model_path = path

    booster = FakeBooster()
    fake_scorer = SimpleNamespace(
        initialized=True,
        feature_names=["score_feature"],
        le_dict={},
        scaler=FakeScaler(),
        cnn_extractor=FakeCnnExtractor(),
        label_encoder=FakeLabelEncoder(),
        xgb_model=FakeXgbModel(booster),
        models_dir="models-dir",
    )
    fake_report = SimpleNamespace(station_id="station-1", severity=4)
    fake_station = SimpleNamespace(id="station-1")

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return fake_station

    class FakeDb:
        def query(self, model):
            return FakeQuery()

    class FakeDMatrix:
        def __init__(self, data, label=None):
            self.data = data
            self.label = label

    monkeypatch.setattr("app.services.training_service.ML_LIBS_AVAILABLE", True)
    monkeypatch.setattr("app.services.training_service.risk_scorer", fake_scorer)
    monkeypatch.setattr(
        "app.services.training_service.DataLoaderService.get_recent_reviews",
        lambda db, num_samples=20: [fake_report],
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.training_service.DataLoaderService.map_database_to_features",
        lambda db, report, station: {"score_feature": 4},
    )
    monkeypatch.setattr("xgboost.DMatrix", FakeDMatrix, raising=False)

    TrainingService.trigger_incremental_update("station-1", FakeDb())

    assert booster.updated is True
    assert fake_scorer.xgb_model.saved_model_path.endswith("xgb_risk_classifier.json")
