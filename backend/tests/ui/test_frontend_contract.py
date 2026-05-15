from __future__ import annotations

from pathlib import Path


APP_SOURCE = Path(__file__).resolve().parents[3] / "frontend" / "src" / "App.jsx"


def test_frontend_wires_critical_api_calls():
    source = APP_SOURCE.read_text(encoding="utf-8")

    expected_endpoints = [
        "/auth/login",
        "/auth/register",
        "/auth/mfa/login-verify",
        "/auth/refresh",
        "/auth/logout",
        "/stations",
        "/reports",
        "/notifications",
        "/me",
        "/me/change-password",
        "/me/delete",
    ]

    for endpoint in expected_endpoints:
        assert endpoint in source


def test_frontend_contains_critical_user_and_admin_views():
    source = APP_SOURCE.read_text(encoding="utf-8")

    expected_labels = [
        "System Login",
        "Create Account",
        "Set Up Microsoft Authenticator",
        "Notifications",
        "Profile Settings",
        "Delete Account",
        "Admin Panel",
        "Manage Stations",
        "Review Feedback",
        "Save Settings",
    ]

    for label in expected_labels:
        assert label in source
