from __future__ import annotations

from app.core.security import create_email_verification_token, create_registration_verification_token
from app.models import UserRole
from tests.factories import DEFAULT_PASSWORD, current_totp


def test_verify_email_accepts_registration_token_and_creates_verified_user(client, db_session):
    token = create_registration_verification_token(
        username="verified_user",
        email="verified_user@example.com",
        password_hash="hashed-password-placeholder",
    )

    response = client.post("/api/auth/verify-email", json={"token": token})

    assert response.status_code == 200
    payload = response.json()
    assert payload["email"] == "verified_user@example.com"
    assert payload["setup_token"]
    assert payload["secret"]
    assert payload["qr_code_data_url"].startswith("data:image/")


def test_verify_email_accepts_legacy_email_token_for_existing_user(client, user_factory):
    user = user_factory(
        email="legacy_verify@example.com",
        email_verified=False,
        mfa_enabled=False,
        mfa_secret=None,
    )
    token = create_email_verification_token(user.email)

    response = client.post("/api/auth/verify-email", json={"token": token})

    assert response.status_code == 200
    payload = response.json()
    assert payload["email"] == user.email
    assert payload["setup_token"]


def test_verify_email_rejects_already_mfa_enabled_account(client, user_factory):
    user = user_factory(email="already_enabled@example.com")
    token = create_email_verification_token(user.email)

    response = client.post("/api/auth/verify-email", json={"token": token})

    assert response.status_code == 400
    assert response.json()["detail"] == "Microsoft Authenticator is already enabled for this account"


def test_setup_registration_mfa_rejects_unverified_account(client, user_factory):
    user = user_factory(
        email_verified=False,
        mfa_enabled=False,
        mfa_secret=None,
        mfa_pending_secret=None,
    )
    from app.core.security import create_mfa_setup_token

    response = client.post(
        "/api/auth/mfa/setup-registration",
        json={"setup_token": create_mfa_setup_token(str(user.id))},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Verify your email before setting up MFA"


def test_complete_registration_mfa_rejects_invalid_code(client, user_factory):
    user = user_factory(
        email_verified=True,
        mfa_enabled=False,
        mfa_secret=None,
        mfa_pending_secret="JBSWY3DPEHPK3PXP",
    )
    from app.core.security import create_mfa_setup_token

    response = client.post(
        "/api/auth/mfa/complete-registration",
        json={
            "setup_token": create_mfa_setup_token(str(user.id)),
            "code": "000000",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid authenticator code"


def test_self_service_mfa_setup_enable_and_disable_flow(client, user_factory, auth_headers_factory, db_session):
    user = user_factory(
        mfa_enabled=False,
        mfa_secret=None,
        mfa_pending_secret=None,
    )
    headers, _refresh_token = auth_headers_factory(user)

    setup_response = client.get("/api/auth/mfa/setup", headers=headers)
    assert setup_response.status_code == 200
    setup_payload = setup_response.json()
    assert setup_payload["secret"]
    assert setup_payload["otp_auth_url"].startswith("otpauth://")

    invalid_enable_response = client.post(
        "/api/auth/mfa/enable",
        headers=headers,
        json={"code": "000000"},
    )
    assert invalid_enable_response.status_code == 400
    assert invalid_enable_response.json()["detail"] == "Invalid authenticator code"

    enable_response = client.post(
        "/api/auth/mfa/enable",
        headers=headers,
        json={"code": current_totp(setup_payload["secret"])},
    )
    assert enable_response.status_code == 200
    assert enable_response.json()["message"] == "Multi-factor authentication enabled successfully"

    db_session.refresh(user)
    assert user.mfa_enabled is True
    assert user.mfa_secret == setup_payload["secret"]
    assert user.mfa_pending_secret is None

    invalid_disable_response = client.post(
        "/api/auth/mfa/disable",
        headers=headers,
        json={"code": "000000"},
    )
    assert invalid_disable_response.status_code == 400
    assert invalid_disable_response.json()["detail"] == "Invalid authenticator code"

    disable_response = client.post(
        "/api/auth/mfa/disable",
        headers=headers,
        json={"code": current_totp(setup_payload["secret"])},
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["message"] == "Multi-factor authentication disabled"

    db_session.refresh(user)
    assert user.mfa_enabled is False
    assert user.mfa_secret is None


def test_enable_mfa_requires_setup_first_and_disable_requires_enabled_state(client, user_factory, auth_headers_factory):
    user = user_factory(
        mfa_enabled=False,
        mfa_secret=None,
        mfa_pending_secret=None,
    )
    headers, _refresh_token = auth_headers_factory(user)

    enable_response = client.post("/api/auth/mfa/enable", headers=headers, json={"code": "123456"})
    assert enable_response.status_code == 400
    assert enable_response.json()["detail"] == "Start MFA setup first"

    disable_response = client.post("/api/auth/mfa/disable", headers=headers, json={"code": "123456"})
    assert disable_response.status_code == 400
    assert disable_response.json()["detail"] == "MFA is not enabled"


def test_refresh_rejects_inactive_user_session(client, user_factory, login_with_mfa, db_session):
    user = user_factory(password=DEFAULT_PASSWORD)
    login_payload = login_with_mfa(user, DEFAULT_PASSWORD)
    user.is_active = False
    db_session.commit()

    response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": login_payload["refresh_token"]},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "User is inactive"


def test_logout_rejects_invalid_refresh_token(client):
    response = client.post(
        "/api/auth/logout",
        json={"refresh_token": "not-a-real-refresh-token"},
    )

    assert response.status_code == 401


def test_forgot_password_requires_mfa_and_reset_validates_email_match(client, user_factory):
    user = user_factory(mfa_enabled=False, mfa_secret=None)

    forgot_response = client.post(
        "/api/auth/forgot-password",
        json={"email": user.email, "code": "123456"},
    )
    assert forgot_response.status_code == 400
    assert forgot_response.json()["detail"] == "Multi-factor authentication is not enabled for this account"

    other_user = user_factory(email="other-reset@example.com")
    forgot_for_other = client.post(
        "/api/auth/forgot-password",
        json={"email": other_user.email, "code": current_totp(other_user.mfa_secret)},
    )
    assert forgot_for_other.status_code == 200
    reset_token = forgot_for_other.json()["reset_token"]

    mismatch_reset = client.post(
        "/api/auth/reset-password",
        json={
            "email": "wrong@example.com",
            "token": reset_token,
            "new_password": "AnotherStrong2",
        },
    )
    assert mismatch_reset.status_code == 400
    assert mismatch_reset.json()["detail"] == "Reset token does not match the provided email"
