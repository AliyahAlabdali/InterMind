"""Mints short-lived Azure AI Speech authorization tokens for the candidate's browser.

Why this exists
---------------
The browser Speech SDK needs a credential to open its recognition websocket, but it must never
be given the Speech resource key: anything shipped to a browser is public. Azure's documented
answer for the JavaScript SDK is ``SpeechConfig.fromAuthorizationToken(token, region)`` with a
*short-lived* token, so this service holds the secret server-side and hands out tokens that
expire in ten minutes.

Two credential paths, same output
---------------------------------
- **Managed identity (preferred in Azure).** Acquire an Entra token for
  ``https://cognitiveservices.azure.com/.default`` and hand it to the browser SDK in the
  ``aad#{resource_id}#{entra_token}`` authorization-token form. No key exists anywhere. Requires
  the Speech resource to have a custom subdomain and the identity to hold the *Cognitive
  Services Speech User* role.
- **Resource key (local development).** Exchange the key at the region's
  ``/sts/v1.0/issueToken`` endpoint. The key never leaves the backend.

The service deliberately does no caching. Tokens are only requested when a candidate presses the
microphone, which is rare enough that a ten-minute cache would add invalidation risk for no real
saving, and a per-request token keeps the blast radius of a leaked token to one answer.
"""

from __future__ import annotations

import logging

import httpx
from pydantic import BaseModel

from app.core.config import Settings
from app.core.exceptions import ConfigurationError, SpeechServiceUnavailable

logger = logging.getLogger(__name__)

# Azure issues tokens valid for 10 minutes; it recommends refreshing at ~9. The browser is told
# the shorter figure so it never tries to reuse one on the edge of expiry.
TOKEN_LIFETIME_SECONDS = 540

ENTRA_SCOPE = "https://cognitiveservices.azure.com/.default"


class SpeechToken(BaseModel):
    """What the browser needs to construct a SpeechConfig - and nothing more.

    Deliberately carries no key, no endpoint secret and no candidate identity. ``token`` is
    short-lived and scoped to the Speech resource only.
    """

    token: str
    region: str
    language: str
    expires_in_seconds: int = TOKEN_LIFETIME_SECONDS


class SpeechTokenService:
    """Issues Speech authorization tokens using whichever credential is configured."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client

    async def issue(self) -> SpeechToken:
        """Return a short-lived authorization token for the browser Speech SDK.

        Raises:
            ConfigurationError: speech is not configured on this deployment.
            SpeechServiceUnavailable: the credential or the token endpoint failed.
        """
        settings = self._settings
        region = settings.azure_speech_region
        if not region:
            raise ConfigurationError(
                "AZURE_SPEECH_REGION is not set but SPEECH_PROVIDER=azure was requested"
            )

        if settings.azure_speech_key:
            token = await self._issue_from_key(region, settings.azure_speech_key)
        else:
            token = self._issue_from_managed_identity()

        return SpeechToken(
            token=token,
            region=region,
            language=settings.azure_speech_language,
        )

    def _token_endpoint(self, region: str) -> str:
        host = self._settings.azure_speech_host or f"{region}.api.cognitive.microsoft.com"
        return f"https://{host}/sts/v1.0/issueToken"

    async def _issue_from_key(self, region: str, key: str) -> str:
        url = self._token_endpoint(region)
        try:
            if self._client is not None:
                response = await self._client.post(
                    url, headers={"Ocp-Apim-Subscription-Key": key}, content=b""
                )
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        url, headers={"Ocp-Apim-Subscription-Key": key}, content=b""
                    )
        except httpx.HTTPError as exc:
            # Note the URL but never the key - and httpx exception text does not include
            # request headers, so this stays safe to log.
            raise SpeechServiceUnavailable(
                f"Could not reach the Speech token endpoint at {url}"
            ) from exc

        if response.status_code != 200:
            raise SpeechServiceUnavailable(
                f"Speech token endpoint returned HTTP {response.status_code}"
            )

        token = response.text.strip()
        if not token:
            raise SpeechServiceUnavailable("Speech token endpoint returned an empty token")
        return token

    def _issue_from_managed_identity(self) -> str:
        resource_id = self._settings.azure_speech_resource_id
        if not resource_id:
            raise ConfigurationError(
                "Neither AZURE_SPEECH_KEY nor AZURE_SPEECH_RESOURCE_ID is set - one is required "
                "to issue Speech tokens"
            )

        try:
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ConfigurationError(
                "Managed-identity Speech auth requires the 'azure' extra "
                "(pip install -e '.[azure]')"
            ) from exc

        try:
            credential = DefaultAzureCredential()
            entra_token = credential.get_token(ENTRA_SCOPE).token
        except Exception as exc:  # noqa: BLE001 - any credential failure is the same to callers
            raise SpeechServiceUnavailable(
                "Managed identity could not acquire a Speech token"
            ) from exc

        # The JavaScript SDK has no TokenCredential overload, so an Entra token reaches it
        # through fromAuthorizationToken in this documented composite form.
        return f"aad#{resource_id}#{entra_token}"
