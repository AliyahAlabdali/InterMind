"""Unit tests for how the Speech token service chooses and uses a credential.

The deployment this protects has *no Speech key at all*: the App Service authenticates with its
managed identity. So the properties under test are the ones that make that path work and keep it
honest:

- managed identity is selected in Azure and the key path in local development, from configuration
  alone, with no code change between environments;
- an Entra token reaches the browser in the composite form Azure expects, addressed to the
  resource's custom domain - because Azure refuses Entra credentials at the regional endpoint,
  a token sent with a region instead of a host would be issued successfully and then fail to
  connect, which is the one failure mode a test has to catch before deployment;
- incoherent configuration fails loudly at issue time rather than issuing something unusable;
- no credential material is ever carried into an error or a response.

Nothing here touches Azure. `azure-identity` is never imported: the credential is injected, which
is also what keeps these tests runnable on a machine with no Azure sign-in.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.config import Settings
from app.core.exceptions import ConfigurationError, SpeechServiceUnavailable
from app.services.speech_token import (
    ENTRA_SCOPE,
    EntraTokenProvider,
    SpeechTokenService,
)

RESOURCE_ID = (
    "/subscriptions/0000/resourceGroups/intermind/providers"
    "/Microsoft.CognitiveServices/accounts/intermind-speech-aliyah"
)
CUSTOM_HOST = "intermind-speech-aliyah.cognitiveservices.azure.com"
ENTRA_TOKEN = "entra.access.token"


class FakeEntra:
    """Stands in for the managed identity. Records how often it was asked."""

    def __init__(self, token: str = ENTRA_TOKEN, *, fail: bool = False) -> None:
        self._token = token
        self._fail = fail
        self.calls = 0

    async def token(self) -> str:
        self.calls += 1
        if self._fail:
            raise SpeechServiceUnavailable("Managed identity could not acquire a Speech token")
        return self._token


def _settings(**overrides) -> Settings:
    """Build settings for one scenario and nothing else.

    Every Azure field is pinned explicitly, including to ``None``, because ``Settings`` reads the
    repository's real ``.env``. Leaving a field out would silently inherit the developer's own
    ``AZURE_SPEECH_KEY`` - which made an earlier draft of the "no credential configured" test pass
    a live key to Azure over the network instead of raising. Tests must not depend on, or reach,
    anybody's Azure resource.
    """
    base = {
        "speech_provider": "azure",
        "azure_speech_auth": "auto",
        "azure_speech_region": None,
        "azure_speech_key": None,
        "azure_speech_resource_id": None,
        "azure_speech_host": None,
        "azure_speech_language": "en-US",
    }
    base.update(overrides)
    return Settings(**base)


def _managed_identity_settings(**overrides) -> Settings:
    """Exactly what the deployed App Service sets: identity, resource id, custom host, no key."""
    base = {
        "azure_speech_auth": "managed_identity",
        "azure_speech_resource_id": RESOURCE_ID,
        "azure_speech_host": CUSTOM_HOST,
    }
    base.update(overrides)
    return _settings(**base)


# --- credential selection -------------------------------------------------------------------


def test_auto_selects_managed_identity_when_a_resource_id_is_set():
    """The production App Service sets a resource id and no key."""
    settings = _settings(
        azure_speech_auth="auto",
        azure_speech_resource_id=RESOURCE_ID,
        azure_speech_host=CUSTOM_HOST,
    )
    assert settings.azure_speech_auth_mode == "managed_identity"


def test_auto_selects_the_key_for_a_local_developer():
    """The local .env sets a region and a key and no resource id - the workflow must not change."""
    settings = _settings(azure_speech_region="eastus", azure_speech_key="local-dev-key")
    assert settings.azure_speech_auth_mode == "key"


def test_pinning_managed_identity_ignores_a_stray_key():
    """Why pinning exists: a key added to App Service later must not downgrade production."""
    settings = _managed_identity_settings(azure_speech_key="a-key-that-should-not-be-used")
    assert settings.azure_speech_auth_mode == "managed_identity"


def test_pinning_key_ignores_a_resource_id():
    settings = _settings(
        azure_speech_auth="key",
        azure_speech_region="eastus",
        azure_speech_key="local-dev-key",
        azure_speech_resource_id=RESOURCE_ID,
    )
    assert settings.azure_speech_auth_mode == "key"


# --- the managed-identity token --------------------------------------------------------------


async def test_managed_identity_issues_an_aad_composite_token():
    entra = FakeEntra()
    token = await SpeechTokenService(_managed_identity_settings(), entra=entra).issue()

    # The browser SDK has no TokenCredential overload; this composite form is how the service
    # side learns which resource the Entra token is for.
    assert token.token == f"aad#{RESOURCE_ID}#{ENTRA_TOKEN}"
    assert entra.calls == 1


async def test_managed_identity_addresses_the_browser_to_the_custom_domain():
    """The regression that matters: Azure rejects Entra tokens at the regional endpoint."""
    token = await SpeechTokenService(_managed_identity_settings(), entra=FakeEntra()).issue()

    assert token.host == CUSTOM_HOST
    assert token.region is None


async def test_managed_identity_ignores_a_configured_region():
    """A leftover AZURE_SPEECH_REGION must not send the browser to the regional endpoint."""
    settings = _managed_identity_settings(azure_speech_region="eastus")
    token = await SpeechTokenService(settings, entra=FakeEntra()).issue()

    assert token.host == CUSTOM_HOST
    assert token.region is None


async def test_the_entra_access_token_is_not_exposed_on_its_own():
    """It is embedded in the authorization token by necessity, and nowhere else."""
    token = await SpeechTokenService(_managed_identity_settings(), entra=FakeEntra()).issue()

    payload = token.model_dump()
    assert payload.pop("token")
    assert ENTRA_TOKEN not in str(payload)
    assert set(payload) == {"region", "host", "language", "expires_in_seconds"}


async def test_the_token_is_short_lived():
    token = await SpeechTokenService(_managed_identity_settings(), entra=FakeEntra()).issue()
    assert 0 < token.expires_in_seconds <= 600


@pytest.mark.parametrize("host", [f"https://{CUSTOM_HOST}/", f"https://{CUSTOM_HOST}", CUSTOM_HOST])
async def test_the_custom_host_is_accepted_however_the_portal_wrote_it(host: str):
    """The portal shows the custom domain as a URL, so a pasted value can carry a scheme."""
    settings = _managed_identity_settings(azure_speech_host=host)
    token = await SpeechTokenService(settings, entra=FakeEntra()).issue()

    assert token.host == CUSTOM_HOST


# --- misconfiguration fails at issue time ----------------------------------------------------


async def test_managed_identity_without_a_custom_host_is_a_configuration_error():
    """Better to refuse than to issue a token that could never connect."""
    settings = _managed_identity_settings(azure_speech_host=None)
    with pytest.raises(ConfigurationError):
        await SpeechTokenService(settings, entra=FakeEntra()).issue()


async def test_managed_identity_without_a_resource_id_is_a_configuration_error():
    settings = _managed_identity_settings(azure_speech_resource_id=None)
    with pytest.raises(ConfigurationError):
        await SpeechTokenService(settings, entra=FakeEntra()).issue()


async def test_no_credential_at_all_is_a_configuration_error():
    """A region alone is not a credential, and must fail before any network call is attempted."""
    settings = _settings(azure_speech_region="eastus")
    with pytest.raises(ConfigurationError):
        await SpeechTokenService(settings, entra=FakeEntra()).issue()


async def test_the_key_path_needs_a_region():
    settings = _settings(azure_speech_key="local-dev-key")
    with pytest.raises(ConfigurationError):
        await SpeechTokenService(settings, entra=FakeEntra()).issue()


async def test_a_missing_credential_provider_is_a_configuration_error():
    """Not a 503: a service wired without a credential provider is a deployment defect."""
    with pytest.raises(ConfigurationError):
        await SpeechTokenService(_managed_identity_settings(), entra=None).issue()


async def test_an_identity_failure_is_a_service_outage_not_a_config_error():
    """A missing role assignment or an IMDS blip must leave the candidate able to type on."""
    service = SpeechTokenService(_managed_identity_settings(), entra=FakeEntra(fail=True))
    with pytest.raises(SpeechServiceUnavailable):
        await service.issue()


# --- the credential provider itself ----------------------------------------------------------


class FakeCredential:
    """Mimics azure-identity's synchronous credential contract."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.scopes: list[tuple[str, ...]] = []
        self.closed = False

    def get_token(self, *scopes: str):
        if self.fail:
            raise RuntimeError("ManagedIdentityCredential authentication failed: tenant abc-123")
        self.scopes.append(scopes)
        return type("AccessToken", (), {"token": ENTRA_TOKEN, "expires_on": 0})()

    def close(self) -> None:
        self.closed = True


async def test_the_provider_requests_the_cognitive_services_scope():
    credential = FakeCredential()
    provider = EntraTokenProvider(credential_factory=lambda: credential)

    assert await provider.token() == ENTRA_TOKEN
    assert credential.scopes == [(ENTRA_SCOPE,)]


async def test_the_credential_is_built_once_and_reused():
    """azure-identity caches the access token inside the credential; a new credential per
    request would throw that cache away and hit IMDS on every microphone press."""
    built = 0

    def factory():
        nonlocal built
        built += 1
        return FakeCredential()

    provider = EntraTokenProvider(credential_factory=factory)
    await asyncio.gather(*(provider.token() for _ in range(5)))

    assert built == 1


async def test_a_credential_failure_does_not_leak_its_detail():
    """Credential errors quote tenant and client ids; none of that may reach a caller."""
    provider = EntraTokenProvider(credential_factory=lambda: FakeCredential(fail=True))

    with pytest.raises(SpeechServiceUnavailable) as raised:
        await provider.token()
    assert "abc-123" not in str(raised.value)
    assert "tenant" not in str(raised.value).lower()


async def test_a_failed_token_request_can_be_retried():
    """The lock must not be left held, or one IMDS blip would wedge voice input for good."""
    provider = EntraTokenProvider(credential_factory=lambda: FakeCredential(fail=True))
    for _ in range(2):
        with pytest.raises(SpeechServiceUnavailable):
            await provider.token()


async def test_closing_releases_the_credential():
    credential = FakeCredential()
    provider = EntraTokenProvider(credential_factory=lambda: credential)
    await provider.token()

    await provider.aclose()
    assert credential.closed


async def test_closing_an_unused_provider_is_harmless():
    """Every deployment constructs one, including those that never use speech at all."""
    await EntraTokenProvider(credential_factory=lambda: FakeCredential()).aclose()


async def test_the_azure_dependency_is_only_imported_when_it_is_used():
    """A key-based or speech-less deployment must not depend on azure-identity being present."""
    provider = EntraTokenProvider()
    assert provider._credential is None
    await provider.aclose()
