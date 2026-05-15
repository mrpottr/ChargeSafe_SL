from __future__ import annotations

from app.models import UserSession
from tests.factories import DEFAULT_PASSWORD, current_totp


def test_login_requires_mfa_and_verifies_code(client, user_factory, db_session):
    user = user_factory(password=DEFAULT_PASSWORD)

    login_response = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": DEFAULT_PASSWORD},
    )

    assert login_response.status_code == 200
    login_payload = login_response.json()
    assert login_payload["mfa_required"] is True
    assert login_payload["access_token"] is None
    assert login_payload["mfa_token"]

    invalid_mfa_response = client.post(
        "/api/auth/mfa/login-verify",
        json={"mfa_token": login_payload["mfa_token"], "code": "000000"},
    )
    assert invalid_mfa_response.status_code == 400
    assert invalid_mfa_response.json()["detail"] == "Invalid authenticator code"

    valid_mfa_response = client.post(
        "/api/auth/mfa/login-verify",
        json={
            "mfa_token": login_payload["mfa_token"],
            "code": current_totp(user.mfa_secret),
        },
    )
    assert valid_mfa_response.status_code == 200
    payload = valid_mfa_response.json()
    assert payload["access_token"]
    assert payload["refresh_token"]
    assert payload["user"]["email"] == user.email

    session_count = db_session.query(UserSession).filter(UserSession.user_id == user.id).count()
    assert session_count == 1


def test_refresh_rotates_refresh_token_and_rejects_the_old_one(client, user_factory, login_with_mfa):
    user = user_factory(password=DEFAULT_PASSWORD)
    login_payload = login_with_mfa(user, DEFAULT_PASSWORD)

    refresh_response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": login_payload["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    refreshed_payload = refresh_response.json()
    assert refreshed_payload["access_token"]
    assert refreshed_payload["refresh_token"]

    protected_response = client.get(
        "/api/me",
        headers={"Authorization": f"Bearer {refreshed_payload['access_token']}"},
    )
    assert protected_response.status_code == 200


def test_forgot_and_reset_password_revokes_existing_sessions(
    client,
    user_factory,
    auth_headers_factory,
    db_session,
):
    user = user_factory(password=DEFAULT_PASSWORD)
    headers, _refresh_token = auth_headers_factory(user)

    protected_before_reset = client.get("/api/me", headers=headers)
    assert protected_before_reset.status_code == 200

    forgot_response = client.post(
        "/api/auth/forgot-password",
        json={"email": user.email, "code": current_totp(user.mfa_secret)},
    )
    assert forgot_response.status_code == 200
    forgot_payload = forgot_response.json()
    assert forgot_payload["email"] == user.email
    assert forgot_payload["reset_token"]

    reset_response = client.post(
        "/api/auth/reset-password",
        json={
            "email": user.email,
            "token": forgot_payload["reset_token"],
            "new_password": "NewStrongPass2",
        },
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["message"] == "Password reset successfully"

    protected_after_reset = client.get("/api/me", headers=headers)
    assert protected_after_reset.status_code == 401

    old_password_login = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": DEFAULT_PASSWORD},
    )
    assert old_password_login.status_code == 401

    new_password_login = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": "NewStrongPass2"},
    )
    assert new_password_login.status_code == 200
    assert new_password_login.json()["mfa_required"] is True


def test_register_rejects_duplicate_verified_email_and_invalid_password(client, user_factory):
    existing_user = user_factory(email="duplicate@example.com")

    duplicate_email_response = client.post(
        "/api/auth/register",
        json={
            "username": "another_user",
            "email": existing_user.email,
            "password": "StrongPass1",
        },
    )
    assert duplicate_email_response.status_code == 400
    assert duplicate_email_response.json()["detail"] == "Email already registered"

    invalid_password_response = client.post(
        "/api/auth/register",
        json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "weakpass",
        },
    )
    assert invalid_password_response.status_code == 422


def test_login_rejects_inactive_users(client, user_factory):
    user = user_factory(is_active=False)

    response = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "User account is inactive"
