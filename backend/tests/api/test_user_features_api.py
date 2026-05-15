from __future__ import annotations

from tests.factories import DEFAULT_PASSWORD


def test_settings_profile_and_messages_persist(
    client,
    seeded_standard_user,
    auth_headers_factory,
):
    headers, _refresh_token = auth_headers_factory(seeded_standard_user)

    settings_response = client.get("/api/settings", headers=headers)
    assert settings_response.status_code == 200
    assert settings_response.json()["alert_threshold"] == 70

    update_settings_response = client.put(
        "/api/settings",
        headers=headers,
        json={
            "alert_threshold": 84,
            "language": "Sinhala",
            "push_notifications_enabled": False,
        },
    )
    assert update_settings_response.status_code == 200
    updated_settings_payload = update_settings_response.json()
    assert updated_settings_payload["alert_threshold"] == 84
    assert updated_settings_payload["language"] == "Sinhala"
    assert updated_settings_payload["push_notifications_enabled"] is False

    update_profile_response = client.put(
        "/api/me",
        headers=headers,
        params={"username": "renamed_user"},
    )
    assert update_profile_response.status_code == 200
    assert update_profile_response.json()["username"] == "renamed_user"

    first_message_response = client.post(
        "/api/messages",
        headers=headers,
        json={"role": "user", "text": "Hello from pytest"},
    )
    assert first_message_response.status_code == 200

    second_message_response = client.post(
        "/api/messages",
        headers=headers,
        json={"role": "bot", "text": "Reply from assistant"},
    )
    assert second_message_response.status_code == 200

    list_messages_response = client.get("/api/messages", headers=headers)
    assert list_messages_response.status_code == 200
    assert [item["text"] for item in list_messages_response.json()] == [
        "Hello from pytest",
        "Reply from assistant",
    ]

    clear_messages_response = client.delete("/api/messages", headers=headers)
    assert clear_messages_response.status_code == 200
    assert clear_messages_response.json()["message"] == "Message history cleared"

    empty_messages_response = client.get("/api/messages", headers=headers)
    assert empty_messages_response.json() == []


def test_notifications_filter_mark_read_and_forbid_cross_user_updates(
    client,
    user_factory,
    notification_factory,
    auth_headers_factory,
):
    owner = user_factory()
    other_user = user_factory()
    own_unread = notification_factory(user_id=owner.id, title="Unread", is_read=False)
    notification_factory(user_id=owner.id, title="Read", is_read=True)
    foreign_notification = notification_factory(user_id=other_user.id, title="Foreign", is_read=False)
    headers, _refresh_token = auth_headers_factory(owner)

    unread_response = client.get("/api/notifications", headers=headers, params={"unread_only": True})
    assert unread_response.status_code == 200
    unread_payload = unread_response.json()
    assert [item["title"] for item in unread_payload] == ["Unread"]

    mark_read_response = client.put(
        f"/api/notifications/{own_unread.id}",
        headers=headers,
        json={"is_read": True},
    )
    assert mark_read_response.status_code == 200
    assert mark_read_response.json()["is_read"] is True

    foreign_update_response = client.put(
        f"/api/notifications/{foreign_notification.id}",
        headers=headers,
        json={"is_read": True},
    )
    assert foreign_update_response.status_code == 403

    mark_all_response = client.post("/api/notifications/mark-all-read", headers=headers)
    assert mark_all_response.status_code == 200
    assert mark_all_response.json()["message"] == "All notifications marked as read"

    unread_after_mark_all = client.get("/api/notifications", headers=headers, params={"unread_only": True})
    assert unread_after_mark_all.status_code == 200
    assert unread_after_mark_all.json() == []


def test_profile_update_rejects_duplicate_username(client, user_factory, auth_headers_factory):
    existing_owner = user_factory(username="existing_name")
    another_user = user_factory(username="another_name")
    headers, _refresh_token = auth_headers_factory(another_user)

    response = client.put(
        "/api/me",
        headers=headers,
        params={"username": existing_owner.username},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Username already taken"
