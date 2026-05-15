from __future__ import annotations

import atexit
import os
import shutil
import socket
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text


_STARTED_EMBEDDED_POSTGRES = False
_EMBEDDED_POSTGRES_DATA_DIR: Path | None = None


def _set_base_test_environment() -> None:
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("ADMIN_PASSWORD", "admin_password_123")
    os.environ.setdefault("SMTP_HOST", "")
    os.environ.setdefault("SMTP_FROM_EMAIL", "")
    os.environ.setdefault("GOOGLE_API_KEY", "")


def _to_psycopg_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _database_is_reachable(database_url: str) -> bool:
    try:
        with psycopg.connect(_to_psycopg_dsn(database_url), connect_timeout=2):
            return True
    except Exception:
        return False


def _tcp_port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) == 0


def _ensure_test_database_exists(database_name: str, port: int) -> str:
    admin_dsn = f"postgresql://postgres@127.0.0.1:{port}/postgres"
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database_name,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{database_name}"')
    return f"postgresql+psycopg://postgres@127.0.0.1:{port}/{database_name}"


def _start_embedded_postgres() -> str:
    global _STARTED_EMBEDDED_POSTGRES, _EMBEDDED_POSTGRES_DATA_DIR

    initdb = shutil.which("initdb")
    pg_ctl = shutil.which("pg_ctl")
    if not initdb or not pg_ctl:
        raise RuntimeError(
            "No reachable PostgreSQL database was found and local PostgreSQL binaries "
            "(`initdb`/`pg_ctl`) are not available."
        )

    port = int(os.getenv("CHARGESAFE_TEST_PGPORT", "55432"))
    database_name = os.getenv("CHARGESAFE_TEST_DB_NAME", "chargesafe_pytest")
    data_root = Path(os.getenv("CHARGESAFE_TEST_PGDATA", tempfile.gettempdir()))
    data_dir = data_root / "chargesafe_sl_pytest_pg"
    log_path = data_dir / "server.log"
    _EMBEDDED_POSTGRES_DATA_DIR = data_dir

    if not (data_dir / "PG_VERSION").exists():
        data_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [initdb, "-D", str(data_dir), "-U", "postgres", "-A", "trust", "-E", "UTF8"],
            check=True,
            capture_output=True,
            text=True,
        )

    if not _tcp_port_is_open("127.0.0.1", port):
        subprocess.run(
            [
                pg_ctl,
                "-D",
                str(data_dir),
                "-l",
                str(log_path),
                "-o",
                f"-p {port} -h 127.0.0.1",
                "-w",
                "start",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        _STARTED_EMBEDDED_POSTGRES = True

    return _ensure_test_database_exists(database_name, port)


def _stop_embedded_postgres() -> None:
    if not _STARTED_EMBEDDED_POSTGRES or _EMBEDDED_POSTGRES_DATA_DIR is None:
        return

    pg_ctl = shutil.which("pg_ctl")
    if not pg_ctl:
        return

    subprocess.run(
        [pg_ctl, "-D", str(_EMBEDDED_POSTGRES_DATA_DIR), "-w", "stop"],
        check=False,
        capture_output=True,
        text=True,
    )


def _configure_database_url() -> str:
    candidates = [
        os.getenv("CHARGESAFE_TEST_DATABASE_URL"),
        os.getenv("TEST_DATABASE_URL"),
        os.getenv("DATABASE_URL"),
    ]
    for candidate in candidates:
        if candidate and _database_is_reachable(candidate):
            os.environ["DATABASE_URL"] = candidate
            return candidate

    database_url = _start_embedded_postgres()
    os.environ["DATABASE_URL"] = database_url
    return database_url


_set_base_test_environment()
TEST_DATABASE_URL = _configure_database_url()
atexit.register(_stop_embedded_postgres)

from app.main import app
from app.core.config import settings
from app.core.rate_limit import limiter
from app.models import (
    ChargingStation,
    CyberRiskLevel,
    Notification,
    Report,
    ScoreHistory,
    User,
    UserRole,
    UserSettings,
)
from app.db.session import SessionLocal
from app.services.risk_state_observer import map_risk_category, notify_on_risk_state_change
from app.services.audit_service import AuditService

from tests.factories import (
    DEFAULT_PASSWORD,
    auth_headers,
    create_authenticated_session,
    create_cyber_criterion,
    create_message,
    create_notification,
    create_report,
    create_score_history,
    create_station,
    create_temperature_history,
    create_user,
    current_totp,
)

settings.auth_rate_limit_per_minute = 1000
settings.api_rate_limit_per_minute = 1000
limiter.enabled = False
app.state.limiter.enabled = False


TRUNCATE_STATEMENT = text(
    """
    TRUNCATE TABLE
        audit_logs,
        user_sessions,
        notifications,
        messages,
        incident_reports,
        score_history,
        temperature_history,
        cyber_scores,
        cyber_criteria,
        user_settings,
        charging_stations,
        users
    RESTART IDENTITY CASCADE
    """
)


def _truncate_database() -> None:
    with SessionLocal() as db:
        db.execute(TRUNCATE_STATEMENT)
        db.commit()


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def app_instance():
    original_startup = list(app.router.on_startup)
    original_shutdown = list(app.router.on_shutdown)
    app.router.on_startup.clear()
    app.router.on_shutdown.clear()
    try:
        yield app
    finally:
        app.router.on_startup[:] = original_startup
        app.router.on_shutdown[:] = original_shutdown


@pytest.fixture(autouse=True)
def clean_database():
    _truncate_database()
    yield
    _truncate_database()


@pytest.fixture(autouse=True)
def stub_feedback_processor(monkeypatch):
    from app.services.feedback_processor import FeedbackProcessor

    def _process_feedback(report_id: str, station_id: str, db):
        report = db.query(Report).filter(Report.id == report_id).first()
        station = db.query(ChargingStation).filter(ChargingStation.id == station_id).first()
        if report is None or station is None:
            return None

        previous_score = float(station.safety_score or 0.0)
        if str(report.report_type.value).lower() == "positive":
            new_score = max(previous_score - 4.0, 0.0)
        else:
            score_increase = float((report.severity or 1) * 6)
            new_score = min(previous_score + score_increase, 100.0)

        station.safety_score = round(new_score, 1)
        station.last_scored_at = datetime.utcnow()
        category = map_risk_category(station.safety_score) or "LOW"
        station.cyber_risk_level = {
            "LOW": CyberRiskLevel.low,
            "MEDIUM": CyberRiskLevel.medium,
            "HIGH": CyberRiskLevel.high,
        }[category]

        db.add(
            ScoreHistory(
                station_id=station.id,
                score=station.safety_score,
                level=category,
                trigger="Auto(Test)",
                recorded_at=station.last_scored_at,
            )
        )
        notify_on_risk_state_change(
            db,
            station_id=station.id,
            old_score=previous_score,
            new_score=station.safety_score,
            timestamp=station.last_scored_at,
        )
        db.commit()
        return {
            "station_id": str(station.id),
            "risk_score": station.safety_score,
            "cyber_risk_level": category,
        }

    monkeypatch.setattr(FeedbackProcessor, "process_feedback", staticmethod(_process_feedback))


@pytest.fixture(autouse=True)
def stable_request_context(monkeypatch):
    def _build_request_context(request) -> dict[str, str | None]:
        return {
            "ip_address": "127.0.0.1",
            "user_agent": request.headers.get("user-agent", "pytest"),
        }

    monkeypatch.setattr(AuditService, "build_request_context", staticmethod(_build_request_context))


@pytest.fixture
def client(app_instance):
    with TestClient(app_instance) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    with SessionLocal() as db:
        yield db


@pytest.fixture
def user_factory(db_session):
    def _factory(**kwargs):
        return create_user(db_session, **kwargs)

    return _factory


@pytest.fixture
def station_factory(db_session):
    def _factory(**kwargs):
        return create_station(db_session, **kwargs)

    return _factory


@pytest.fixture
def report_factory(db_session):
    def _factory(**kwargs):
        return create_report(db_session, **kwargs)

    return _factory


@pytest.fixture
def notification_factory(db_session):
    def _factory(**kwargs):
        return create_notification(db_session, **kwargs)

    return _factory


@pytest.fixture
def message_factory(db_session):
    def _factory(**kwargs):
        return create_message(db_session, **kwargs)

    return _factory


@pytest.fixture
def cyber_criterion_factory(db_session):
    def _factory(**kwargs):
        return create_cyber_criterion(db_session, **kwargs)

    return _factory


@pytest.fixture
def score_history_factory(db_session):
    def _factory(**kwargs):
        return create_score_history(db_session, **kwargs)

    return _factory


@pytest.fixture
def temperature_history_factory(db_session):
    def _factory(**kwargs):
        return create_temperature_history(db_session, **kwargs)

    return _factory


@pytest.fixture
def auth_session_factory(db_session):
    def _factory(user: User):
        return create_authenticated_session(db_session, user)

    return _factory


@pytest.fixture
def auth_headers_factory(auth_session_factory):
    def _factory(user: User):
        access_token, refresh_token = auth_session_factory(user)
        return auth_headers(access_token), refresh_token

    return _factory


@pytest.fixture
def login_with_mfa(client):
    def _login(user: User, password: str = DEFAULT_PASSWORD):
        response = client.post(
            "/api/auth/login",
            json={"email": user.email, "password": password},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        if data.get("mfa_required"):
            verify_response = client.post(
                "/api/auth/mfa/login-verify",
                json={
                    "mfa_token": data["mfa_token"],
                    "code": current_totp(user.mfa_secret),
                },
            )
            assert verify_response.status_code == 200, verify_response.text
            data = verify_response.json()
        return data

    return _login


@pytest.fixture
def seeded_standard_user(user_factory) -> User:
    return user_factory()


@pytest.fixture
def seeded_admin_user(user_factory) -> User:
    return user_factory(role=UserRole.admin)


@pytest.fixture
def seeded_station(station_factory):
    return station_factory()
