"""Typed application configuration.

Every setting is read from environment variables (and therefore from ``.env``),
so nothing secret is ever hard-coded. Validation happens once, at import time,
which turns configuration mistakes into clear startup errors instead of runtime
surprises.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from app import __version__
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root = backend/app/core/config.py -> up four levels.
REPO_ROOT = Path(__file__).resolve().parents[3]

PLACEHOLDER_SECRETS = {
    "change-me-to-a-long-random-string",
    "changeme",
    "secret",
    "your-secret-key",
}


class Settings(BaseSettings):
    """Application settings, loaded from environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", Path(".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ------------------------------------------------------
    app_name: str = "AgriPredict"
    environment: Literal["development", "testing", "production"] = "development"
    debug: bool = True
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    version: str = __version__

    # --- Security ---------------------------------------------------------
    secret_key: str = "change-me-to-a-long-random-string"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    jwt_algorithm: str = "HS256"
    cors_origins: str = "http://localhost:8081,http://localhost:19006"
    auth_rate_limit_per_minute: int = 10
    # bcrypt work factor. 12 is appropriate for production; the test suite
    # lowers it to keep the build fast (see backend/tests/conftest.py).
    bcrypt_rounds: int = 12

    # --- Database ---------------------------------------------------------
    database_url: str = "sqlite:///./agripredict.db"
    db_echo: bool = False

    # --- Weather ----------------------------------------------------------
    weather_provider: Literal["openweathermap", "open-meteo", "mock"] = "openweathermap"
    openweather_api_key: str = ""
    weather_timeout_seconds: float = 10.0
    weather_cache_minutes: int = 30

    # --- Buyer discovery --------------------------------------------------
    google_places_api_key: str = ""
    places_timeout_seconds: float = 10.0
    places_default_radius_m: int = 25_000
    places_max_results: int = 20

    # --- ML service -------------------------------------------------------
    ml_service_url: str = "http://localhost:8001"
    ml_service_timeout_seconds: float = 30.0
    ml_service_enabled: bool = True
    forecast_cache_minutes: int = 60

    # --- Reports ----------------------------------------------------------
    report_storage_dir: Path = Field(default=Path("./generated_reports"))
    report_ttl_minutes: int = 60

    # --- Seed -------------------------------------------------------------
    seed_demo_data: bool = False

    # ---------------------------------------------------------------------
    # Derived helpers
    # ---------------------------------------------------------------------
    @field_validator("secret_key")
    @classmethod
    def _reject_placeholder_in_production(cls, value: str) -> str:
        # Environment is validated in the model_validator below, so only shape
        # is checked here; use the collected value there.
        if not value or len(value) < 16:
            raise ValueError(
                "SECRET_KEY must be at least 16 characters. Generate one with: "
                "python -c \"import secrets;print(secrets.token_urlsafe(48))\""
            )
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def report_dir(self) -> Path:
        path = self.report_storage_dir
        if not path.is_absolute():
            path = REPO_ROOT / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def has_weather_key(self) -> bool:
        return bool(self.openweather_api_key.strip())

    @property
    def has_places_key(self) -> bool:
        return bool(self.google_places_api_key.strip())

    def validate_runtime(self) -> None:
        """Fail fast on configurations that are unsafe in production.

        Called from the application factory so that a misconfigured deployment
        refuses to boot rather than serving traffic with a guessable secret.
        """
        if self.is_production and self.secret_key in PLACEHOLDER_SECRETS:
            raise RuntimeError(
                "SECRET_KEY is a placeholder. Set a unique SECRET_KEY before "
                "running in production."
            )
        if self.is_production and self.debug:
            raise RuntimeError("DEBUG must be false in production.")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton (cached)."""
    return Settings()


settings = get_settings()
