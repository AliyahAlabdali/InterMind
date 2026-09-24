"""Application configuration, loaded from environment variables (and an optional .env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ONET_KB_PATH = _REPO_ROOT / "data" / "processed" / "onet" / "onet_kb.jsonl"


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
    onet_kb_path: Path = DEFAULT_ONET_KB_PATH

    # Origins allowed to call the API cross-origin, comma-separated. In production the browser
    # talks to the frontend's own origin and Vercel rewrites /api to this backend, so CORS is
    # not exercised by the app at all - this exists for direct access (tooling, a staging
    # frontend) and must stay an explicit list. Never "*": a wildcard cannot be combined with
    # credentialed requests, and doing it anyway with session cookies would be a real hole.
    # Defaults to the local dev server only, so a deployment that forgets to set it fails
    # closed rather than open.
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def allowed_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    # --- Persistence ------------------------------------------------------------------------
    # PostgreSQL connection string, e.g.
    #   postgresql://user:password@host:5432/intermind?ssl=require
    # `postgres://` and a missing `+asyncpg` driver are both normalised automatically (see
    # app.db.engine), so an URL copied straight out of Azure works unchanged.
    #
    # Unset means **no persistence**: the app falls back to the in-memory repositories, nothing
    # survives a restart, and startup says so loudly. That is the mode the test suite runs in.
    # Any real deployment must set it.
    database_url: str | None = None
    # Echo SQL to the log. Development only - statements can contain candidate answers.
    database_echo: bool = False

    # --- Recruiter sessions -----------------------------------------------------------------
    # There is no configured recruiter account and no credential in configuration. Recruiters
    # register themselves at /auth/recruiter/signup and their accounts live in the recruiter
    # repository (PostgreSQL when DATABASE_URL is set), so the only settings here are about how
    # long a browser session lasts and how its cookie is marked. See docs/recruiter-auth.md.

    # How long a recruiter browser session lasts before it has to sign in again (see
    # app.api.recruiter_session). Eight hours is a working day; sessions are in-memory, so a
    # backend restart ends them all regardless.
    recruiter_session_ttl_seconds: int = 8 * 60 * 60
    # Whether the session cookie carries the `Secure` flag. Must be true anywhere the app is
    # served over HTTPS - which is everywhere except a local http://localhost machine, where a
    # Secure cookie would simply never be stored. Defaults to false so local development works;
    # set RECRUITER_SESSION_COOKIE_SECURE=true in any real deployment.
    recruiter_session_cookie_secure: bool = False

    # --- Speech-to-text -------------------------------------------------------------------
    # Which STT implementation the candidate UI should use. "azure" is production; "browser"
    # keeps the (much weaker) Web Speech implementation available for offline development;
    # "disabled" turns voice input off entirely and leaves typing as the only input.
    speech_provider: Literal["azure", "browser", "disabled"] = "browser"

    # Azure AI Speech. The key is backend-only and is NEVER returned to a client - the browser
    # receives a short-lived authorization token minted from it (see
    # app.services.speech_token). Leave the key unset in Azure and rely on managed identity.
    azure_speech_region: str | None = None
    azure_speech_key: str | None = None
    # Required for managed-identity auth: the Speech resource's full ARM resource id. The
    # browser SDK has no TokenCredential overload, so an Entra token is passed to it in the
    # `aad#{resource_id}#{token}` authorization-token form.
    azure_speech_resource_id: str | None = None
    # Optional custom subdomain host (e.g. "my-speech.cognitiveservices.azure.com"). Required
    # when the resource uses a custom domain, which managed identity itself requires.
    azure_speech_host: str | None = None
    azure_speech_language: str = "en-US"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (safe to use as a FastAPI dependency)."""
    return Settings()
