"""Configuration loading for MT5 credentials from the local .env file."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MT5Settings(BaseSettings):
    """MT5 connection settings loaded from environment or .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    login: int = Field(alias="MT5_LOGIN")
    password: str = Field(alias="MT5_PASSWORD")
    server: str = Field(alias="MT5_SERVER")
    calibration_mode: str | None = Field(default=None, alias="MT5_CALIBRATION_MODE")


def load_settings() -> MT5Settings:
    """Load MT5 settings without logging or printing secrets."""

    return MT5Settings()
