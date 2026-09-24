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
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_onet_kb, get_speech_token_service
from app.core.config import Settings, get_settings
from app.knowledge.onet_kb import OnetKnowledgeBase
from app.services.speech_token import SpeechTokenService
from tests.conftest import FIXTURES

FIXTURE_KB_PATH = FIXTURES / "onet_kb_fixture.jsonl"

FAKE_KEY = "super-secret-speech-key-should-never-leak"
FAKE_TOKEN = "fake.jwt.value"


@pytest.fixture(autouse=True)
def _use_fixture_kb(app):
    app.dependency_overrides[get_onet_kb] = lambda: OnetKnowledgeBase(path=FIXTURE_KB_PATH)


def _azure_settings(**overrides) -> Settings:
    base = {
        "speech_provider": "azure",
        "azure_speech_region": "westeurope",
        "azure_speech_key": FAKE_KEY,
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


async def test_response_never_contains_the_speech_key(app, client):
    app.dependency_overrides[get_settings] = lambda: _azure_settings()
    app.dependency_overrides[get_speech_token_service] = lambda: _service_returning()

    interview_id, _ = await _start_interview(client)
    resp = await client.get(f"/interviews/{interview_id}/speech-token")

    assert FAKE_KEY not in resp.text
    assert "Ocp-Apim-Subscription-Key" not in resp.text
    assert set(resp.json()) == {"token", "region", "language", "expires_in_seconds"}


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
        _azure_settings(azure_speech_key=None, azure_speech_resource_id=None)
    )
    with pytest.raises(ConfigurationError):
        await service.issue()
