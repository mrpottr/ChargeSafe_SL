from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="ChargeSafe SL API", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/chargesafe_sl",
        alias="DATABASE_URL",
    )
    backend_cors_origins_raw: str = Field(
        default="http://localhost:5173",
        alias="BACKEND_CORS_ORIGINS",
    )
    secret_key: str = Field(
        default="your-secret-key-change-in-production",
        alias="SECRET_KEY",
    )
    google_api_key: str = Field(
        default="",
        alias="GOOGLE_API_KEY",
    )
    algorithm: str = Field(
        default="HS256",
        alias="ALGORITHM",
    )

    @property
    def backend_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins_raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
