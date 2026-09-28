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
    # Refuse to start without a database. The in-memory fallback is right for a fresh clone and
    # for the test suite, and catastrophic in production: the app would come up looking healthy,
    # serve real candidates, and lose every account, interview and report on the next restart -
    # and App Service restarts containers routinely. A warning in the log is not enough, because
    # nothing fails until the data is already gone.
    #
    # Opt-in rather than opt-out so local development and tests keep working untouched. Set
    # REQUIRE_DATABASE=true in every real deployment; see docs/deployment.md.
    require_database: bool = False

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

    # Which credential the backend uses to mint browser tokens (see app.services.speech_token):
    #   managed_identity - Entra ID via the App Service managed identity. No secret exists.
    #   key              - the Speech resource key. Local development only.
    #   auto             - managed identity when AZURE_SPEECH_RESOURCE_ID is set, else the key.
    # `auto` is what makes one codebase serve both environments: production sets the resource id
    # and no key, local development sets a key and no resource id. Pin it to `managed_identity`
    # in Azure if you want a stray key setting to be an error rather than a silent downgrade to
    # secret-based auth.
    azure_speech_auth: Literal["auto", "managed_identity", "key"] = "auto"

    # Azure AI Speech. The key is backend-only and is NEVER returned to a client - the browser
    # receives a short-lived authorization token minted from it (see
    # app.services.speech_token). Leave the key unset in Azure and rely on managed identity.
    # Region is required for key auth (it selects the regional token endpoint the browser then
    # talks to) and unused by managed identity, which is addressed by custom domain instead.
    azure_speech_region: str | None = None
    azure_speech_key: str | None = None
    # Required for managed-identity auth: the Speech resource's full ARM resource id. The
    # browser SDK has no TokenCredential overload, so an Entra token is passed to it in the
    # `aad#{resource_id}#{token}` authorization-token form.
    azure_speech_resource_id: str | None = None
    # Custom subdomain host, e.g. "my-speech.cognitiveservices.azure.com". **Required for
    # managed identity**: Entra tokens are only accepted at a resource's custom-domain endpoint,
    # never at the regional one, so this is what the browser is told to connect to. Optional for
    # key auth, where it overrides the regional token-issuing endpoint.
    azure_speech_host: str | None = None
    azure_speech_language: str = "en-US"

    @property
    def azure_speech_host_name(self) -> str | None:
        """`azure_speech_host` as a bare hostname, however the operator wrote it.

        Azure's portal shows the custom domain as a full URL, so a pasted value can arrive as
        "https://x.cognitiveservices.azure.com/". Both consumers need a bare host - one builds an
        https URL from it, the other a wss one - so the scheme and any trailing path are stripped
        here rather than being guarded for twice.
        """
        host = (self.azure_speech_host or "").strip()
        if not host:
            return None
        host = host.split("://", 1)[-1]
        return host.split("/", 1)[0].rstrip(".") or None

    @property
    def azure_speech_auth_mode(self) -> Literal["managed_identity", "key"]:
        """Resolve `azure_speech_auth`, collapsing `auto` to a concrete credential."""
        if self.azure_speech_auth != "auto":
            return self.azure_speech_auth
        return "managed_identity" if self.azure_speech_resource_id else "key"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (safe to use as a FastAPI dependency)."""
    return Settings()
