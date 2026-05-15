from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.csrf import (
    CSRFMiddleware,
    _origin_is_allowed,
    _request_has_non_csrf_cookies,
    _uses_bearer_auth,
)
from app.core.https_enforcement import HTTPSRedirectMiddleware, is_request_secure
from app.core.security_headers import API_CONTENT_SECURITY_POLICY, SecurityHeadersMiddleware
from app.services.gemini_chat import (
    _build_local_fallback_reply,
    _find_station_match,
    _is_direct_station_score_question,
    _risk_band,
    generate_chat_reply,
)


def test_gemini_helpers_and_local_fallbacks(db_session, station_factory):
    high_station = station_factory(name="Colombo Central Station", risk_score=88.0, city="Colombo")
    low_station = station_factory(name="Galle Safe Point", risk_score=14.0, city="Galle")

    stations = [high_station, low_station]
    assert _find_station_match("What is Colombo Central Station risk score?", stations) == high_station
    assert _find_station_match("Tell me about Galle safe", stations) == low_station
    assert _risk_band(None) == "unknown"
    assert _risk_band(25) == "low"
    assert _risk_band(50) == "medium"
    assert _risk_band(80) == "high"
    assert _is_direct_station_score_question("What is the risk score of Colombo Central Station?") is True

    no_db_reply = _build_local_fallback_reply("hello", db=None)
    assert "couldn't reach the live ai service" in no_db_reply.lower()

    matched_reply = _build_local_fallback_reply("Tell me about Colombo Central Station", db_session)
    assert "88.0/100" in matched_reply
    assert "high risk" in matched_reply.lower()

    safest_reply = _build_local_fallback_reply("Which are the safest stations?", db_session)
    assert "lowest-risk stations" in safest_reply
    assert low_station.name in safest_reply

    riskiest_reply = _build_local_fallback_reply("Which stations are highest risk?", db_session)
    assert "highest-risk stations" in riskiest_reply
    assert high_station.name in riskiest_reply


def test_generate_chat_reply_uses_local_fallback_and_live_client(db_session, station_factory, monkeypatch):
    station = station_factory(name="Negombo Hub", risk_score=61.0)

    monkeypatch.setattr(settings, "google_api_key", "")
    direct_station_reply = generate_chat_reply("What is the risk score for Negombo Hub?", db_session)
    assert "61.0/100" in direct_station_reply

    generic_fallback_reply = generate_chat_reply("hello there", db_session)
    assert "highest scored station" in generic_fallback_reply.lower()

    monkeypatch.setattr(settings, "google_api_key", "fake-key")

    class FakeHttpOptions:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeThinkingConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeGenerateContentConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeModels:
        def __init__(self, text):
            self._text = text

        def generate_content(self, **kwargs):
            return SimpleNamespace(text=self._text)

    class FakeClient:
        def __init__(self, api_key, http_options):
            self.models = FakeModels("live ai reply")

    monkeypatch.setattr("app.services.gemini_chat.genai.Client", FakeClient)
    monkeypatch.setattr(
        "app.services.gemini_chat.types",
        SimpleNamespace(
            HttpOptions=FakeHttpOptions,
            ThinkingConfig=FakeThinkingConfig,
            GenerateContentConfig=FakeGenerateContentConfig,
        ),
    )

    live_reply = generate_chat_reply("Give me a quick overview", db_session)
    assert live_reply == "live ai reply"

    class ExplodingClient:
        def __init__(self, api_key, http_options):
            raise RuntimeError("gemini down")

    monkeypatch.setattr("app.services.gemini_chat.genai.Client", ExplodingClient)
    fallback_reply = generate_chat_reply("Which stations are highest risk?", db_session)
    assert "highest-risk stations" in fallback_reply


def test_csrf_helper_functions():
    request = SimpleNamespace(
        cookies={"sessionid": "abc", settings.csrf_cookie_name: "csrf"},
        headers={"authorization": "Bearer token", "origin": settings.frontend_base_url},
    )

    assert _request_has_non_csrf_cookies(request) is True
    assert _uses_bearer_auth(request) is True
    assert _origin_is_allowed(request) is True


def test_csrf_middleware_enforces_origin_and_token(monkeypatch):
    original_origins = settings.backend_cors_origins_raw
    settings.backend_cors_origins_raw = "http://frontend.test"

    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.get("/safe")
    def safe():
        return {"ok": True}

    @app.post("/submit")
    def submit():
        return {"ok": True}

    client = TestClient(app)

    safe_response = client.get("/safe")
    assert safe_response.status_code == 200
    assert settings.csrf_cookie_name in safe_response.cookies

    invalid_origin_response = client.post(
        "/submit",
        cookies={"sessionid": "abc", settings.csrf_cookie_name: "token"},
        headers={"origin": "http://evil.test", settings.csrf_header_name: "token"},
    )
    assert invalid_origin_response.status_code == 403
    assert invalid_origin_response.json()["detail"] == "CSRF origin check failed"

    invalid_token_response = client.post(
        "/submit",
        cookies={"sessionid": "abc", settings.csrf_cookie_name: "token"},
        headers={"origin": "http://frontend.test", settings.csrf_header_name: "wrong"},
    )
    assert invalid_token_response.status_code == 403
    assert invalid_token_response.json()["detail"] == "CSRF validation failed"

    valid_response = client.post(
        "/submit",
        cookies={"sessionid": "abc", settings.csrf_cookie_name: "token"},
        headers={"origin": "http://frontend.test", settings.csrf_header_name: "token"},
    )
    assert valid_response.status_code == 200

    bearer_bypass_response = client.post(
        "/submit",
        cookies={"sessionid": "abc"},
        headers={"authorization": "Bearer token"},
    )
    assert bearer_bypass_response.status_code == 200

    settings.backend_cors_origins_raw = original_origins


def test_https_redirect_middleware_and_secure_detection(monkeypatch):
    original_enforce = settings.enforce_https
    settings.enforce_https = True

    app = FastAPI()
    app.add_middleware(HTTPSRedirectMiddleware)

    @app.get("/hello")
    def hello():
        return {"ok": True}

    client = TestClient(app)

    redirected = client.get("/hello", follow_redirects=False)
    assert redirected.status_code == 307
    assert redirected.headers["location"].startswith("https://")

    secure_request = SimpleNamespace(url=SimpleNamespace(scheme="http"), headers={"x-forwarded-proto": "https"})
    insecure_request = SimpleNamespace(url=SimpleNamespace(scheme="http"), headers={})
    https_request = SimpleNamespace(url=SimpleNamespace(scheme="https"), headers={})

    assert is_request_secure(https_request) is True
    assert is_request_secure(secure_request) is True
    assert is_request_secure(insecure_request) is False

    settings.enforce_https = original_enforce


def test_security_headers_middleware_adds_headers_and_secures_cookies():
    original_app_env = settings.app_env
    original_enforce = settings.enforce_https
    settings.app_env = "production"
    settings.enforce_https = True

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/cookie")
    def cookie(response: Response):
        response.set_cookie("sessionid", "abc123")
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/cookie", headers={"x-forwarded-proto": "https"})

    assert response.status_code == 200
    assert response.headers["Content-Security-Policy"] == API_CONTENT_SECURITY_POLICY
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "Strict-Transport-Security" in response.headers
    assert "Secure" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]

    secured_cookie = SecurityHeadersMiddleware._secure_cookie_header("csrf_token=abc")
    assert "Secure" in secured_cookie
    assert "HttpOnly" not in secured_cookie

    settings.app_env = original_app_env
    settings.enforce_https = original_enforce
