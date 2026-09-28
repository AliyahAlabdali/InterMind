"""Mints short-lived Azure AI Speech credentials for the candidate's browser.

Why this exists
---------------
The browser Speech SDK needs a credential to open its recognition websocket, but it must never
be given the Speech resource key: anything shipped to a browser is public. Azure's documented
answer is an *authorization token* - a short-lived value the SDK accepts in place of a key - so
this service holds the secret (or the identity) server-side and hands out tokens that expire in
minutes.

Two credential paths, two different browser targets
---------------------------------------------------
- **Managed identity (production).** Acquire an Entra token for
  ``https://cognitiveservices.azure.com/.default`` and hand it to the browser SDK in the
  ``aad#{resource_id}#{entra_token}`` authorization-token form. No key exists anywhere. Requires
  the Speech resource to have a custom subdomain and the identity to hold the *Cognitive
  Services Speech User* role.

  The browser must then connect to that **custom-domain host**, not to the regional endpoint:
  Azure only accepts Entra credentials at a resource's own subdomain. That is why ``issue``
  returns ``host`` and why it is a configuration error to select managed identity without
  ``AZURE_SPEECH_HOST``.
- **Resource key (local development).** Exchange the key at the region's
  ``/sts/v1.0/issueToken`` endpoint for a regional token, and tell the browser the region. The
  key never leaves the backend.

The two paths are deliberately not interchangeable at the network level, which is why the
response carries ``host`` *or* ``region`` rather than assuming one shape fits both.

Caching
-------
The Entra credential is created once per process (see :class:`EntraTokenProvider`) because
``azure-identity`` caches and refreshes the access token inside the credential object - a fresh
credential per request would mean an IMDS round trip on every microphone press. The Speech
authorization token itself is not cached: it is only minted when a candidate presses the
microphone, which is rare enough that a cache would add invalidation risk for no real saving,
and a per-request token keeps the blast radius of a leaked token to one answer.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Protocol

import httpx
from pydantic import BaseModel

from app.core.config import Settings
from app.core.exceptions import ConfigurationError, SpeechServiceUnavailable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Azure issues tokens valid for 10 minutes; it recommends refreshing at ~9. The browser is told
# the shorter figure so it never tries to reuse one on the edge of expiry.
TOKEN_LIFETIME_SECONDS = 540

ENTRA_SCOPE = "https://cognitiveservices.azure.com/.default"


class SpeechToken(BaseModel):
    """What the browser needs to construct a SpeechConfig - and nothing more.

    Deliberately carries no key, no identity and no candidate details. ``token`` is short-lived
    and scoped to the Speech resource only.

    Exactly one of ``host`` and ``region`` is the browser's connection target, and the frontend
    prefers ``host``: an Entra-issued token is only valid against the resource's custom domain,
    while a key-issued token is regional. Both are optional on the wire so that neither
    credential path has to send a value that is meaningless for it.
    """

    token: str
    region: str | None = None
    host: str | None = None
    language: str
    expires_in_seconds: int = TOKEN_LIFETIME_SECONDS


class SupportsEntraToken(Protocol):
    """The one thing this service needs from a credential, so tests can supply their own."""

    async def token(self) -> str: ...


class EntraTokenProvider:
    """Process-lifetime holder for the Azure credential behind managed-identity auth.

    Two jobs, both about not paying for a credential more than once:

    - **Reuse.** ``azure-identity`` caches the access token inside the credential and refreshes
      it shortly before expiry, so holding one instance for the process turns all but the first
      microphone press into an in-memory lookup.
    - **Keep the event loop free.** The synchronous credential is used on purpose, run through
      ``asyncio.to_thread``. The async credentials in ``azure.identity.aio`` need ``aiohttp``,
      which nothing else here uses, and a cached-token call is cheap enough that a thread hop
      costs less than a second HTTP stack. Calling ``get_token`` inline would instead block every
      other request on this single-process backend for the length of an IMDS round trip.

    ``azure-identity`` credentials are documented thread-safe, and the lock here serialises the
    uncached case so a burst of first requests makes one token request rather than N.
    """

    def __init__(self, credential_factory: Callable[[], Any] | None = None) -> None:
        self._credential_factory = credential_factory
        self._credential: Any | None = None
        self._lock = asyncio.Lock()

    def _build_credential(self) -> Any:
        if self._credential_factory is not None:
            return self._credential_factory()
        try:
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:  # pragma: no cover - exercised only without the dependency
            raise ConfigurationError(
                "Managed-identity Speech auth requires the 'azure-identity' package"
            ) from exc
        # DefaultAzureCredential rather than ManagedIdentityCredential: in App Service it
        # resolves to the assigned managed identity, and on a developer machine it picks up an
        # `az login`, which is what lets managed-identity auth be tested outside Azure at all.
        return DefaultAzureCredential()

    async def token(self) -> str:
        async with self._lock:
            try:
                if self._credential is None:
                    self._credential = await asyncio.to_thread(self._build_credential)
                credential = self._credential
                access_token = await asyncio.to_thread(credential.get_token, ENTRA_SCOPE)
            except ConfigurationError:
                raise
            except Exception as exc:  # noqa: BLE001 - any credential failure is the same here
                # No detail from the exception is surfaced to the caller: credential errors can
                # quote tenant and client ids, and the endpoint turns this into a flat 503.
                logger.warning("Managed identity could not acquire a Speech token", exc_info=exc)
                raise SpeechServiceUnavailable(
                    "Managed identity could not acquire a Speech token"
                ) from exc
        return access_token.token

    async def aclose(self) -> None:
        """Release the credential's own HTTP resources. Safe to call when never used."""
        credential = self._credential
        self._credential = None
        if credential is None:
            return
        close = getattr(credential, "close", None)
        if close is None:
            return
        try:
            await asyncio.to_thread(close)
        except Exception as exc:  # noqa: BLE001 - shutdown must not raise
            logger.warning("Failed to close the Speech credential", exc_info=exc)


class SpeechTokenService:
    """Issues Speech authorization tokens using whichever credential is configured."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        entra: SupportsEntraToken | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._entra = entra

    async def issue(self) -> SpeechToken:
        """Return a short-lived authorization token for the browser Speech SDK.

        Raises:
            ConfigurationError: speech is not configured coherently on this deployment.
            SpeechServiceUnavailable: the credential or the token endpoint failed.
        """
        settings = self._settings
        if settings.azure_speech_auth_mode == "managed_identity":
            return await self._issue_with_managed_identity()
        return await self._issue_with_key()

    # --- managed identity (production) ------------------------------------------------------

    async def _issue_with_managed_identity(self) -> SpeechToken:
        settings = self._settings
        resource_id = settings.azure_speech_resource_id
        if not resource_id:
            raise ConfigurationError(
                "AZURE_SPEECH_AUTH=managed_identity requires AZURE_SPEECH_RESOURCE_ID"
            )

        host = settings.azure_speech_host_name
        if not host:
            # Not a nicety: Azure rejects Entra credentials at the regional endpoint, so without
            # a custom domain to send the browser to, a token issued here could never connect.
            raise ConfigurationError(
                "Managed-identity Speech auth requires AZURE_SPEECH_HOST - Entra tokens are only "
                "accepted at the Speech resource's custom-domain endpoint"
            )

        if self._entra is None:
            raise ConfigurationError(
                "No Entra credential provider is configured for managed-identity Speech auth"
            )

        entra_token = await self._entra.token()

        return SpeechToken(
            # The browser SDK has no TokenCredential overload, so an Entra token reaches it
            # through an authorization token in this documented composite form; the service side
            # unpacks the resource id to route the request.
            token=f"aad#{resource_id}#{entra_token}",
            host=host,
            # Region is deliberately omitted: with managed identity the browser connects by host,
            # and sending a region the frontend must then ignore invites the wrong one to be used.
            region=None,
            language=settings.azure_speech_language,
        )

    # --- resource key (local development) --------------------------------------------------

    async def _issue_with_key(self) -> SpeechToken:
        settings = self._settings
        region = settings.azure_speech_region
        if not region:
            raise ConfigurationError(
                "AZURE_SPEECH_REGION is not set but SPEECH_PROVIDER=azure was requested"
            )
        key = settings.azure_speech_key
        if not key:
            raise ConfigurationError(
                "Neither AZURE_SPEECH_KEY nor AZURE_SPEECH_RESOURCE_ID is set - one is required "
                "to issue Speech tokens"
            )

        token = await self._exchange_key_for_token(region, key)
        return SpeechToken(
            token=token,
            region=region,
            # A key-issued token is regional, so the browser connects by region. The host, if
            # set, named only the endpoint *this backend* just used.
            host=None,
            language=settings.azure_speech_language,
        )

    def _token_endpoint(self, region: str) -> str:
        host = self._settings.azure_speech_host_name or f"{region}.api.cognitive.microsoft.com"
        return f"https://{host}/sts/v1.0/issueToken"

    async def _exchange_key_for_token(self, region: str, key: str) -> str:
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
