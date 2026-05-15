import unittest

from app.core.config import Settings


class CorsConfigTests(unittest.TestCase):
    def test_cors_lists_are_parsed_and_frontend_origin_is_preserved(self):
        settings = Settings(
            BACKEND_CORS_ORIGINS="http://localhost:5173,https://app.example.com",
            BACKEND_CORS_METHODS="GET,POST,OPTIONS",
            BACKEND_CORS_HEADERS="Authorization,Content-Type",
            FRONTEND_BASE_URL="https://app.example.com",
        )

        self.assertEqual(
            settings.backend_cors_origins,
            ["http://localhost:5173", "https://app.example.com"],
        )
        self.assertEqual(settings.backend_cors_methods, ["GET", "POST", "OPTIONS"])
        self.assertEqual(settings.backend_cors_headers, ["Authorization", "Content-Type"])


if __name__ == "__main__":
    unittest.main()
