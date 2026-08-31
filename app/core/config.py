"""Application configuration, loaded from environment variables (and an optional .env)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings. Secrets come from the environment, never from source."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: Literal["fake", "openai"] = "fake"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (safe to use as a FastAPI dependency)."""
    return Settings()
