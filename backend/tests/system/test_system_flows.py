from __future__ import annotations

from app.models import UserRole
from tests.factories import DEFAULT_PASSWORD


def test_health_ready_and_root_endpoints_boot_under_test_config(client):
    root_response = client.get("/")
    assert root_response.status_code == 200
    assert root_response.json()["status"] == "running"

    health_response = client.get("/api/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}

    ready_response = client.get("/api/ready")
    assert ready_response.status_code == 200
    assert ready_response.json() == {"status": "ready"}


def test_role_based_access_and_user_deactivation_flow(client, user_factory, auth_headers_factory):
    admin = user_factory(role=UserRole.admin, password=DEFAULT_PASSWORD)
    target_user = user_factory(password=DEFAULT_PASSWORD)
    admin_headers, _refresh_token = auth_headers_factory(admin)
    user_headers, _user_refresh = auth_headers_factory(target_user)

    deactivate_response = client.delete(f"/api/admin/users/{target_user.id}", headers=admin_headers)
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["message"] == "User deactivated"

    protected_after_deactivation = client.get("/api/me", headers=user_headers)
    assert protected_after_deactivation.status_code == 403
    assert protected_after_deactivation.json()["detail"] == "User is inactive"

    login_after_deactivation = client.post(
        "/api/auth/login",
        json={"email": target_user.email, "password": DEFAULT_PASSWORD},
    )
    assert login_after_deactivation.status_code == 403
    assert login_after_deactivation.json()["detail"] == "User account is inactive"


def test_change_password_revokes_other_sessions_but_keeps_current_one(
    client,
    user_factory,
    auth_headers_factory,
):
    user = user_factory(password=DEFAULT_PASSWORD)
    current_headers, _first_refresh = auth_headers_factory(user)
    other_headers, _second_refresh = auth_headers_factory(user)

    change_password_response = client.post(
        "/api/me/change-password",
        headers=current_headers,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "AnotherPass2"},
    )
    assert change_password_response.status_code == 200
    assert change_password_response.json()["message"] == "Password changed successfully"

    current_session_response = client.get("/api/me", headers=current_headers)
    assert current_session_response.status_code == 200

    other_session_response = client.get("/api/me", headers=other_headers)
    assert other_session_response.status_code == 401

    new_login_response = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": "AnotherPass2"},
    )
    assert new_login_response.status_code == 200
    assert new_login_response.json()["mfa_required"] is True
