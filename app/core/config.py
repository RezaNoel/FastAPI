"""Environment-backed settings.

Local development runs with the defaults. Production refuses to start on the
development secret.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-change-me-before-any-real-deployment"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Grove"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = DEV_SECRET
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    database_url: str = "sqlite+aiosqlite:///./grove.db"
    cors_origins: str = "http://127.0.0.1:8000,http://localhost:8000"
    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 30
    media_dir: str = "media"
    log_level: str = "INFO"
    auto_create_tables: bool = True
    seed_on_startup: bool = True
    trust_proxy: bool = False
    low_stock_kg: float = 15

    @field_validator("app_env")
    @classmethod
    def _env(cls, value: str) -> str:
        value = value.strip().lower()
        allowed = {"development", "test", "production"}
        if value not in allowed:
            raise ValueError(f"APP_ENV must be one of {sorted(allowed)}")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def media_path(self) -> Path:
        return Path(self.media_dir)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def assert_runtime_safety(self) -> None:
        if self.app_env != "production":
            return
        if self.secret_key == DEV_SECRET or len(self.secret_key) < 32:
            raise RuntimeError("Set a strong SECRET_KEY before running in production.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
