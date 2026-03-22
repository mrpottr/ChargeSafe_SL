from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

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

    @property
    def backend_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins_raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
