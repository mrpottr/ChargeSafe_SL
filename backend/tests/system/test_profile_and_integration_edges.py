from __future__ import annotations

from app.models import Message, Notification, Report, User, UserSettings
from tests.factories import DEFAULT_PASSWORD


def test_delete_account_removes_related_records_and_blocks_future_access(
    client,
    user_factory,
    station_factory,
    report_factory,
    notification_factory,
    message_factory,
    auth_headers_factory,
    db_session,
):
    user = user_factory(password=DEFAULT_PASSWORD)
    station = station_factory()
    report_factory(user_id=user.id, station_id=station.id)
    notification_factory(user_id=user.id)
    message_factory(user_id=user.id, role="user", text="Delete me")
    headers, _refresh_token = auth_headers_factory(user)
    user_id = user.id

    delete_response = client.post(
        "/api/me/delete",
        headers=headers,
        json={"current_password": DEFAULT_PASSWORD},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "Account deleted successfully"

    assert db_session.query(User).filter(User.id == user_id).first() is None
    assert db_session.query(UserSettings).filter(UserSettings.user_id == user_id).count() == 0
    assert db_session.query(Report).filter(Report.user_id == user_id).count() == 0
    assert db_session.query(Notification).filter(Notification.user_id == user_id).count() == 0
    assert db_session.query(Message).filter(Message.user_id == user_id).count() == 0

    login_response = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": DEFAULT_PASSWORD},
    )
    assert login_response.status_code == 401


def test_delete_and_change_password_validate_current_password(
    client,
    seeded_standard_user,
    auth_headers_factory,
):
    headers, _ = auth_headers_factory(seeded_standard_user)

    delete_response = client.post(
        "/api/me/delete",
        headers=headers,
        json={"current_password": "WrongPass1"},
    )
    assert delete_response.status_code == 400
    assert delete_response.json()["detail"] == "INCORRECT CURRENT PASSWORD"

    change_response = client.post(
        "/api/me/change-password",
        headers=headers,
        json={"current_password": DEFAULT_PASSWORD, "new_password": DEFAULT_PASSWORD},
    )
    assert change_response.status_code == 400
    assert change_response.json()["detail"] == "New password must be different from current password"


def test_settings_and_messages_validation_edges(client, seeded_standard_user, auth_headers_factory):
    headers, _ = auth_headers_factory(seeded_standard_user)

    invalid_settings_response = client.put(
        "/api/settings",
        headers=headers,
        json={"alert_threshold": 101},
    )
    assert invalid_settings_response.status_code == 422

    invalid_message_response = client.post(
        "/api/messages",
        headers=headers,
        json={"role": "system", "text": "Nope"},
    )
    assert invalid_message_response.status_code == 422

    invalid_notification_uuid = client.put(
        "/api/notifications/not-a-uuid",
        headers=headers,
        json={"is_read": True},
    )
    assert invalid_notification_uuid.status_code == 422


def test_missing_settings_return_404(client, user_factory, auth_headers_factory):
    user = user_factory(create_settings=False)
    headers, _ = auth_headers_factory(user)

    get_response = client.get("/api/settings", headers=headers)
    assert get_response.status_code == 404
    assert get_response.json()["detail"] == "Settings not found"

    put_response = client.put(
        "/api/settings",
        headers=headers,
        json={"language": "English"},
    )
    assert put_response.status_code == 404
