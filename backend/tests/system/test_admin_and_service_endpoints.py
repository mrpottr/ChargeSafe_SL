from __future__ import annotations

from app.models import UserRole


def test_sync_openchargemap_requires_admin_and_returns_service_stats(
    client,
    user_factory,
    auth_headers_factory,
    monkeypatch,
):
    regular_user = user_factory()
    regular_headers, _ = auth_headers_factory(regular_user)

    forbidden_response = client.post("/api/sync-openchargemap", headers=regular_headers)
    assert forbidden_response.status_code == 403

    admin = user_factory(role=UserRole.admin)
    admin_headers, _ = auth_headers_factory(admin)

    monkeypatch.setattr(
        "app.api.routes.DataLoaderService.sync_openchargemap_to_database",
        staticmethod(lambda db, force_update=True: {"created": 2, "updated": 1}),
    )
    monkeypatch.setattr(
        "app.api.routes.CyberScoringService.score_all_stations",
        staticmethod(lambda db: {"scored": 3}),
    )

    success_response = client.post("/api/sync-openchargemap", headers=admin_headers)
    assert success_response.status_code == 200
    payload = success_response.json()
    assert payload["message"] == "Sync completed"
    assert payload["stats"] == {"created": 2, "updated": 1}
    assert payload["cyber_stats"] == {"scored": 3}


def test_chat_requires_auth_and_handles_success_and_failures(
    client,
    seeded_standard_user,
    auth_headers_factory,
    monkeypatch,
):
    unauthenticated_response = client.post("/api/chat", json={"message": "hello"})
    assert unauthenticated_response.status_code == 401

    headers, _ = auth_headers_factory(seeded_standard_user)

    monkeypatch.setattr("app.api.routes.generate_chat_reply", lambda message, db: f"echo:{message}")
    success_response = client.post("/api/chat", headers=headers, json={"message": "hello"})
    assert success_response.status_code == 200
    assert success_response.json()["reply"] == "echo:hello"

    def raise_value_error(message, db):
        raise ValueError("Bad prompt")

    monkeypatch.setattr("app.api.routes.generate_chat_reply", raise_value_error)
    value_error_response = client.post("/api/chat", headers=headers, json={"message": "hello"})
    assert value_error_response.status_code == 500
    assert value_error_response.json()["detail"] == "Bad prompt"

    def raise_runtime_error(message, db):
        raise RuntimeError("upstream failed")

    monkeypatch.setattr("app.api.routes.generate_chat_reply", raise_runtime_error)
    runtime_error_response = client.post("/api/chat", headers=headers, json={"message": "hello"})
    assert runtime_error_response.status_code == 502
    assert runtime_error_response.json()["detail"] == "AI service unavailable"
