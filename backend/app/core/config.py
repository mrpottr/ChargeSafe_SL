from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Centralizing environment parsing here keeps the rest of the backend focused
    # on business logic while this class handles defaults and safe fallbacks.
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="ChargeSafe SL API", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/chargesafe_sl",
        alias="DATABASE_URL",
    )
    backend_cors_origins_raw: str = Field(
        default="http://localhost:5173",
        alias="BACKEND_CORS_ORIGINS",
    )
    backend_cors_methods_raw: str = Field(
        default="GET,POST,PUT,PATCH,DELETE,OPTIONS",
        alias="BACKEND_CORS_METHODS",
    )
    backend_cors_headers_raw: str = Field(
        default="Authorization,Content-Type,Accept,Origin",
        alias="BACKEND_CORS_HEADERS",
    )
    secret_key: str = Field(
        default="your-secret-key-change-in-production",
        alias="SECRET_KEY",
    )
    frontend_base_url: str = Field(
        default="http://localhost:5173",
        alias="FRONTEND_BASE_URL",
    )
    google_api_key: str = Field(
        default="",
        alias="GOOGLE_API_KEY",
    )
    algorithm: str = Field(
        default="HS256",
        alias="ALGORITHM",
    )
    access_token_expire_minutes: int = Field(
        default=20,
        alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    refresh_token_expire_days: int = Field(
        default=7,
        alias="REFRESH_TOKEN_EXPIRE_DAYS",
    )
    session_idle_timeout_minutes: int = Field(
        default=20,
        alias="SESSION_IDLE_TIMEOUT_MINUTES",
    )
    api_rate_limit_per_minute: int = Field(
        default=120,
        alias="API_RATE_LIMIT_PER_MINUTE",
    )
    auth_rate_limit_per_minute: int = Field(
        default=30,
        alias="AUTH_RATE_LIMIT_PER_MINUTE",
    )
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")
    error_rate_window_seconds: int = Field(default=60, alias="ERROR_RATE_WINDOW_SECONDS")
    error_rate_threshold: int = Field(default=10, alias="ERROR_RATE_THRESHOLD")
    enforce_https: bool = Field(default=False, alias="ENFORCE_HTTPS")
    trust_x_forwarded_proto: bool = Field(default=True, alias="TRUST_X_FORWARDED_PROTO")
    csrf_cookie_name: str = Field(default="csrf_token", alias="CSRF_COOKIE_NAME")
    csrf_header_name: str = Field(default="X-CSRF-Token", alias="CSRF_HEADER_NAME")
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from_email: str = Field(default="", alias="SMTP_FROM_EMAIL")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")

    @property
    def backend_cors_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.backend_cors_origins_raw.split(",") if origin.strip()]
        if self.frontend_base_url and self.frontend_base_url not in origins:
            origins.append(self.frontend_base_url)
        return origins

    @property
    def backend_cors_methods(self) -> list[str]:
        return [method.strip().upper() for method in self.backend_cors_methods_raw.split(",") if method.strip()]

    @property
    def backend_cors_headers(self) -> list[str]:
        return [header.strip() for header in self.backend_cors_headers_raw.split(",") if header.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @property
    def should_enforce_https(self) -> bool:
        return self.enforce_https or self.is_production


@lru_cache
def get_settings() -> Settings:
    # Settings are cached once per process so repeated imports do not re-read the
    # environment or drift across different parts of the application.
    return Settings()


settings = get_settings()
