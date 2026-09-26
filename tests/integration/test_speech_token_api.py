"""Integration tests for the Azure Speech token endpoint.

The security property under test is simple and absolute: the Speech resource key exists only on
the backend, and no response may ever carry it. Everything else here exists to make sure a
misconfigured or unreachable Azure never turns into a broken interview - the candidate must
always be able to keep typing.

No test touches a real Azure subscription; the token endpoint is faked at the HTTP boundary.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_onet_kb, get_speech_token_service
from app.core.config import Settings, get_settings
from app.core.exceptions import SpeechServiceUnavailable
from app.knowledge.onet_kb import OnetKnowledgeBase
from app.services.speech_token import SpeechTokenService
from tests.conftest import FIXTURES

FIXTURE_KB_PATH = FIXTURES / "onet_kb_fixture.jsonl"

FAKE_KEY = "super-secret-speech-key-should-never-leak"
FAKE_TOKEN = "fake.jwt.value"

# The deployed App Service authenticates with a managed identity: no key, a resource id and a
# custom-domain host. These mirror that configuration.
FAKE_ENTRA_TOKEN = "entra.access.token.should.never.appear.bare"
RESOURCE_ID = (
    "/subscriptions/0000/resourceGroups/intermind/providers"
    "/Microsoft.CognitiveServices/accounts/intermind-speech-aliyah"
)
CUSTOM_HOST = "intermind-speech-aliyah.cognitiveservices.azure.com"


class FakeEntra:
    """Stands in for the App Service managed identity - never contacts Azure."""

    async def token(self) -> str:
        return FAKE_ENTRA_TOKEN


def _managed_identity_settings(**overrides) -> Settings:
    base = {
        "speech_provider": "azure",
        "azure_speech_auth": "managed_identity",
        "azure_speech_resource_id": RESOURCE_ID,
        "azure_speech_host": CUSTOM_HOST,
        # No key, as in the App Service - and pinned so the real .env cannot supply one.
        "azure_speech_key": None,
        "azure_speech_region": None,
        "azure_speech_language": "en-US",
    }
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(autouse=True)
def _use_fixture_kb(app):
    app.dependency_overrides[get_onet_kb] = lambda: OnetKnowledgeBase(path=FIXTURE_KB_PATH)


def _azure_settings(**overrides) -> Settings:
    """Local-development configuration: a region and a key, no resource id.

    Deliberately sets no AZURE_SPEECH_AUTH, so these tests also assert that `auto` still
    resolves to the key path for exactly the settings a developer has in their .env today.
    """
    base = {
        "speech_provider": "azure",
        "azure_speech_region": "westeurope",
        "azure_speech_key": FAKE_KEY,
        # Pinned explicitly: Settings reads the repository's real .env, so an omitted field would
        # inherit the developer's own value and could send a live key to Azure.
        "azure_speech_resource_id": None,
        "azure_speech_host": None,
        "azure_speech_language": "en-US",
    }
    base.update(overrides)
    return Settings(**base)


def _service_returning(token: str = FAKE_TOKEN, *, status: int = 200) -> SpeechTokenService:
    """A token service whose HTTP call is faked - never reaches Azure."""

    async def handler(request: httpx.Request) -> httpx.Response:
        # The key must travel in the request to Azure, and only there.
        assert request.headers["Ocp-Apim-Subscription-Key"] == FAKE_KEY
        return httpx.Response(status, text=token)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SpeechTokenService(_azure_settings(), client=client)


async def _start_interview(client) -> tuple[str, str]:
    jd = "Backend Software Engineer\nPython and Git experience required."
    job_id = (await client.post("/jobs", json={"job_description": jd})).json()["id"]
    await client.post(f"/jobs/{job_id}/interview-plan")
    resp = await client.post("/interviews", json={"job_id": job_id, "candidate_name": "Ada"})
    body = resp.json()
    return body["interview_id"], body["candidate_access_token"]


async def test_issues_a_short_lived_token_for_the_candidate(app, client):
    app.dependency_overrides[get_settings] = lambda: _azure_settings()
    app.dependency_overrides[get_speech_token_service] = lambda: _service_returning()

    interview_id, _ = await _start_interview(client)
    resp = await client.get(f"/interviews/{interview_id}/speech-token")

    assert resp.status_code == 200
    body = resp.json()
    assert body["token"] == FAKE_TOKEN
    assert body["region"] == "westeurope"
    assert body["language"] == "en-US"
    assert 0 < body["expires_in_seconds"] <= 600
    # A key-issued token is regional, so there is no custom host for the browser to prefer.
    assert body["host"] is None


async def test_response_never_contains_the_speech_key(app, client):
    app.dependency_overrides[get_settings] = lambda: _azure_settings()
    app.dependency_overrides[get_speech_token_service] = lambda: _service_returning()

    interview_id, _ = await _start_interview(client)
    resp = await client.get(f"/interviews/{interview_id}/speech-token")

    assert FAKE_KEY not in resp.text
    assert "Ocp-Apim-Subscription-Key" not in resp.text
    assert set(resp.json()) == {"token", "region", "host", "language", "expires_in_seconds"}


async def test_candidate_token_works_for_its_own_interview(app, client):
    app.dependency_overrides[get_settings] = lambda: _azure_settings()
    app.dependency_overrides[get_speech_token_service] = lambda: _service_returning()

    interview_id, candidate_token = await _start_interview(client)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {candidate_token}"},
    ) as candidate:
        resp = await candidate.get(f"/interviews/{interview_id}/speech-token")
    assert resp.status_code == 200


async def test_unauthenticated_request_is_rejected(app, client):
    app.dependency_overrides[get_settings] = lambda: _azure_settings()
    app.dependency_overrides[get_speech_token_service] = lambda: _service_returning()

    interview_id, _ = await _start_interview(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        resp = await anon.get(f"/interviews/{interview_id}/speech-token")
    assert resp.status_code == 401
    assert FAKE_KEY not in resp.text


async def test_a_candidate_cannot_mint_a_token_for_another_interview(app, client):
    """The endpoint is interview-scoped - this is why it hangs off /interviews/{id}."""
    app.dependency_overrides[get_settings] = lambda: _azure_settings()
    app.dependency_overrides[get_speech_token_service] = lambda: _service_returning()

    interview_a, token_a = await _start_interview(client)
    interview_b, _ = await _start_interview(client)
    assert interview_a != interview_b

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token_a}"},
    ) as candidate_a:
        assert (await candidate_a.get(f"/interviews/{interview_b}/speech-token")).status_code == 401


async def test_missing_azure_configuration_is_a_sanitized_500(app, client):
    app.dependency_overrides[get_settings] = lambda: _azure_settings(azure_speech_region=None)
    app.dependency_overrides[get_speech_token_service] = lambda: SpeechTokenService(
        _azure_settings(azure_speech_region=None)
    )

    interview_id, _ = await _start_interview(client)
    resp = await client.get(f"/interviews/{interview_id}/speech-token")

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Service is not configured correctly."
    assert "AZURE_SPEECH_REGION" not in resp.text


async def test_azure_credential_failure_is_a_sanitized_503(app, client):
    app.dependency_overrides[get_settings] = lambda: _azure_settings()
    app.dependency_overrides[get_speech_token_service] = lambda: _service_returning(
        token="denied", status=401
    )

    interview_id, _ = await _start_interview(client)
    resp = await client.get(f"/interviews/{interview_id}/speech-token")

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Voice input is temporarily unavailable."
    assert FAKE_KEY not in resp.text


async def test_unreachable_azure_is_a_sanitized_503(app, client):
    def _unreachable() -> SpeechTokenService:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host", request=request)

        return SpeechTokenService(
            _azure_settings(), client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )

    app.dependency_overrides[get_settings] = lambda: _azure_settings()
    app.dependency_overrides[get_speech_token_service] = lambda: _unreachable()

    interview_id, _ = await _start_interview(client)
    resp = await client.get(f"/interviews/{interview_id}/speech-token")

    assert resp.status_code == 503
    assert FAKE_KEY not in resp.text


async def test_token_is_refused_when_provider_is_not_azure(app, client):
    """Guards against a deployment that never configured Azure silently issuing nothing
    useful - and keeps SPEECH_PROVIDER the single source of truth."""
    app.dependency_overrides[get_settings] = lambda: _azure_settings(speech_provider="browser")
    app.dependency_overrides[get_speech_token_service] = lambda: _service_returning()

    interview_id, _ = await _start_interview(client)
    resp = await client.get(f"/interviews/{interview_id}/speech-token")

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Service is not configured correctly."


async def test_managed_identity_path_requires_a_resource_id(app):
    """Without a key and without a resource id there is no credential at all - that is an
    operator configuration error, not a transient outage."""
    from app.core.exceptions import ConfigurationError

    service = SpeechTokenService(
        _azure_settings(azure_speech_key=None, azure_speech_resource_id=None), entra=FakeEntra()
    )
    with pytest.raises(ConfigurationError):
        await service.issue()


# --- managed identity, as the deployed App Service is configured -----------------------------


def _managed_identity_overrides(app, settings: Settings) -> None:
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_speech_token_service] = lambda: SpeechTokenService(
        settings, entra=FakeEntra()
    )


async def test_managed_identity_issues_a_token_addressed_to_the_custom_domain(app, client):
    """The production path: no key anywhere, and the browser is sent to the custom domain.

    `host` rather than `region` is the whole point - Azure refuses Entra credentials at the
    regional endpoint, so a response carrying a region here would be accepted by the frontend
    and then fail to connect.
    """
    _managed_identity_overrides(app, _managed_identity_settings())

    interview_id, _ = await _start_interview(client)
    resp = await client.get(f"/interviews/{interview_id}/speech-token")

    assert resp.status_code == 200
    body = resp.json()
    assert body["host"] == CUSTOM_HOST
    assert body["region"] is None
    assert body["token"] == f"aad#{RESOURCE_ID}#{FAKE_ENTRA_TOKEN}"
    assert body["language"] == "en-US"
    assert 0 < body["expires_in_seconds"] <= 600


async def test_managed_identity_response_carries_no_key(app, client):
    """There is no key to leak in this configuration, and the shape must stay that way."""
    _managed_identity_overrides(app, _managed_identity_settings())

    interview_id, _ = await _start_interview(client)
    resp = await client.get(f"/interviews/{interview_id}/speech-token")

    assert FAKE_KEY not in resp.text
    assert set(resp.json()) == {"token", "region", "host", "language", "expires_in_seconds"}


async def test_managed_identity_still_requires_candidate_access(app, client):
    """Changing the backend's own credential must not widen who can mint a browser token."""
    _managed_identity_overrides(app, _managed_identity_settings())

    interview_id, _ = await _start_interview(client)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        assert (await anon.get(f"/interviews/{interview_id}/speech-token")).status_code == 401


async def test_managed_identity_without_a_host_is_a_sanitized_500(app, client):
    """An Entra token is only valid at the custom domain, so this is refused up front - and the
    reason never names an environment variable to a candidate."""
    _managed_identity_overrides(app, _managed_identity_settings(azure_speech_host=None))

    interview_id, _ = await _start_interview(client)
    resp = await client.get(f"/interviews/{interview_id}/speech-token")

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Service is not configured correctly."
    assert "AZURE_SPEECH_HOST" not in resp.text


async def test_an_identity_failure_is_a_sanitized_503(app, client):
    """A missing role assignment must leave the candidate typing, not staring at a 500."""

    class FailingEntra:
        async def token(self) -> str:
            raise SpeechServiceUnavailable("Managed identity could not acquire a Speech token")

    settings = _managed_identity_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_speech_token_service] = lambda: SpeechTokenService(
        settings, entra=FailingEntra()
    )

    interview_id, _ = await _start_interview(client)
    resp = await client.get(f"/interviews/{interview_id}/speech-token")

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Voice input is temporarily unavailable."


async def test_the_app_shares_one_credential_provider_across_requests(app, client):
    """Wiring check on the real dependency: it must hand out the process-lifetime provider, or
    azure-identity's token cache is discarded on every microphone press."""
    from app.api.deps import get_speech_credential_provider

    provider = app.state.speech_credential_provider
    assert provider is not None

    seen = []

    # Resolved by FastAPI through the real dependency, so this covers the wiring rather than
    # re-implementing it.
    def _record(
        entra=Depends(get_speech_credential_provider),  # noqa: B008 - FastAPI's DI pattern
    ) -> SpeechTokenService:
        seen.append(entra)
        return SpeechTokenService(_managed_identity_settings(), entra=FakeEntra())

    # Wrapped in a lambda: `_managed_identity_settings` takes **overrides, and FastAPI would read
    # that as a request parameter and reject every call with a 422.
    app.dependency_overrides[get_settings] = lambda: _managed_identity_settings()
    app.dependency_overrides[get_speech_token_service] = _record

    interview_id, _ = await _start_interview(client)
    for _ in range(2):
        assert (await client.get(f"/interviews/{interview_id}/speech-token")).status_code == 200

    assert seen == [provider, provider]
