import unittest
from uuid import uuid4

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


def route_dependency_names(route: APIRoute) -> set[str]:
    names: set[str] = set()
    stack = list(route.dependant.dependencies)
    while stack:
        dependency = stack.pop()
        if dependency.call:
            names.add(getattr(dependency.call, "__name__", dependency.call.__class__.__name__))
        stack.extend(dependency.dependencies)
    return names


def find_route(path: str, method: str) -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method.upper() in route.methods:
            return route
    raise AssertionError(f"Route {method} {path} not found")


class DummySession:
    pass


def override_get_db():
    yield DummySession()


class ApiSecurityHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_startup = list(app.router.on_startup)
        cls.original_shutdown = list(app.router.on_shutdown)
        app.router.on_startup.clear()
        app.router.on_shutdown.clear()
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_db, None)
        app.router.on_startup[:] = cls.original_startup
        app.router.on_shutdown[:] = cls.original_shutdown
        cls.client.close()

    def test_public_routes_remain_unauthenticated_by_design(self):
        public_routes = [
            ("/api/health", "GET"),
            ("/api/ready", "GET"),
            ("/api/auth/register", "POST"),
            ("/api/auth/login", "POST"),
            ("/api/auth/forgot-password", "POST"),
            ("/api/auth/reset-password", "POST"),
            ("/api/stations", "GET"),
            ("/api/stations/{station_id}", "GET"),
            ("/api/stations/{station_id}/score-history", "GET"),
            ("/api/stations/{station_id}/temperature-history", "GET"),
        ]

        for path, method in public_routes:
            dependency_names = route_dependency_names(find_route(path, method))
            self.assertNotIn("get_current_user", dependency_names, f"{method} {path} should remain public")
            self.assertNotIn("get_current_admin", dependency_names, f"{method} {path} should remain public")

    def test_protected_routes_require_auth_by_design(self):
        protected_routes = [
            ("/api/chat", "POST", "get_current_user"),
            ("/api/sync-openchargemap", "POST", "get_current_admin"),
            ("/api/internal/process-new-feedback", "POST", "get_current_admin"),
            ("/api/auth/mfa/setup", "GET", "get_current_user"),
            ("/api/auth/mfa/enable", "POST", "get_current_user"),
            ("/api/auth/mfa/disable", "POST", "get_current_user"),
            ("/api/me", "GET", "get_current_user"),
            ("/api/reports", "POST", "get_current_user"),
            ("/api/stations/{station_id}/cyber-score", "GET", "get_current_user"),
        ]

        for path, method, required_dependency in protected_routes:
            dependency_names = route_dependency_names(find_route(path, method))
            self.assertIn(required_dependency, dependency_names, f"{method} {path} should require {required_dependency}")

    def test_protected_routes_return_401_without_token(self):
        station_id = uuid4()
        report_id = uuid4()

        protected_requests = [
            ("post", "/api/chat", {"json": {"message": "hello"}}),
            ("post", "/api/sync-openchargemap", {}),
            ("post", "/api/internal/process-new-feedback", {"json": {"report_id": str(report_id), "station_id": str(station_id)}}),
            ("get", "/api/me", {}),
            ("get", "/api/auth/mfa/setup", {}),
            ("get", f"/api/stations/{station_id}/cyber-score", {}),
        ]

        for method, path, kwargs in protected_requests:
            response = getattr(self.client, method)(path, **kwargs)
            self.assertEqual(response.status_code, 401, f"{method.upper()} {path} should return 401 without a token")


if __name__ == "__main__":
    unittest.main()
