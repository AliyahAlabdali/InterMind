"""Recruiter accounts: registration, sign-in, sessions, and the credential boundary.

Replaces the single-configured-account tests. A recruiter is now a persistent row created by
``POST /auth/recruiter/signup``, so every test here registers the accounts it needs.

Tenant isolation lives in ``test_tenant_isolation.py``; this file is about authentication.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_onet_kb
from app.api.recruiter_session import RecruiterSession, RecruiterSessionStore
from app.api.routes.auth import RECRUITER_SESSION_COOKIE
from app.domain.recruiter import MIN_PASSWORD_LENGTH
from app.knowledge.onet_kb import OnetKnowledgeBase
from tests.conftest import (
    FIXTURES,
    TEST_RECRUITER_EMAIL,
    TEST_RECRUITER_PASSWORD,
    recruiter_credentials,
)

FIXTURE_KB_PATH = FIXTURES / "onet_kb_fixture.jsonl"
JD = "Backend Software Engineer\nPython and Git experience required. Critical thinking a must."
RECRUITER_ENDPOINT = "/jobs"


@pytest.fixture(autouse=True)
def _use_fixture_kb(app):
    app.dependency_overrides[get_onet_kb] = lambda: OnetKnowledgeBase(path=FIXTURE_KB_PATH)


def _client(app, token: str | None = None) -> AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers)


# --- signup -------------------------------------------------------------------------------


async def test_signup_creates_an_account_and_signs_it_in(app):
    async with _client(app) as client:
        response = await client.post("/auth/recruiter/signup", json=recruiter_credentials())

        assert response.status_code == 201
        assert response.json()["authenticated"] is True
        # Straight into the workspace - no "now sign in with what you just typed".
        assert (await client.get(RECRUITER_ENDPOINT)).status_code == 200


async def test_the_account_is_stored_as_a_hash_never_a_plaintext_password(app):
    async with _client(app) as client:
        await client.post("/auth/recruiter/signup", json=recruiter_credentials())

    stored = await app.state.recruiter_repository.get_by_email(TEST_RECRUITER_EMAIL)
    assert stored is not None
    assert stored.password_hash.startswith("scrypt$")
    assert TEST_RECRUITER_PASSWORD not in stored.password_hash
    # The model has nowhere to put a plaintext password, and nothing put one anywhere else.
    assert TEST_RECRUITER_PASSWORD not in stored.model_dump_json()


async def test_email_is_normalised_so_casing_cannot_create_a_second_account(app):
    async with _client(app) as first:
        assert (
            await first.post("/auth/recruiter/signup", json=recruiter_credentials())
        ).status_code == 201

    async with _client(app) as second:
        response = await second.post(
            "/auth/recruiter/signup",
            json=recruiter_credentials(f"  {TEST_RECRUITER_EMAIL.upper()}  "),
        )

    assert response.status_code == 409


async def test_duplicate_signup_is_rejected(app):
    async with _client(app) as client:
        await client.post("/auth/recruiter/signup", json=recruiter_credentials())
        response = await client.post("/auth/recruiter/signup", json=recruiter_credentials())

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


@pytest.mark.parametrize("password", ["short", "x" * (MIN_PASSWORD_LENGTH - 1)])
async def test_password_policy_is_enforced_server_side(app, password):
    """The frontend mirrors this rule; only the backend enforces it."""
    async with _client(app) as client:
        response = await client.post(
            "/auth/recruiter/signup",
            json={"email": TEST_RECRUITER_EMAIL, "password": password},
        )

    assert response.status_code == 422
    assert str(MIN_PASSWORD_LENGTH) in response.json()["detail"]
    assert await app.state.recruiter_repository.get_by_email(TEST_RECRUITER_EMAIL) is None


@pytest.mark.parametrize(
    "email", ["not-an-email", "no@domain", "spa ce@example.com", "@example.com"]
)
async def test_malformed_emails_are_rejected(app, email):
    async with _client(app) as client:
        response = await client.post(
            "/auth/recruiter/signup", json={"email": email, "password": TEST_RECRUITER_PASSWORD}
        )

    assert response.status_code == 422


async def test_an_oversized_password_is_rejected_before_it_is_hashed(app):
    """Resource protection: nobody gets to make the server scrypt a megabyte."""
    async with _client(app) as client:
        response = await client.post(
            "/auth/recruiter/signup",
            json={"email": TEST_RECRUITER_EMAIL, "password": "x" * 100_000},
        )

    assert response.status_code == 422


async def test_signup_returns_no_credential_or_account_detail(app):
    async with _client(app) as client:
        response = await client.post("/auth/recruiter/signup", json=recruiter_credentials())

    body = response.json()
    assert set(body) <= {"authenticated", "expires_in_seconds"}
    assert TEST_RECRUITER_PASSWORD not in response.text
    assert "scrypt$" not in response.text


# --- sign-in ------------------------------------------------------------------------------


async def test_login_succeeds_after_signup(app):
    async with _client(app) as client:
        await client.post("/auth/recruiter/signup", json=recruiter_credentials())
        await client.post("/auth/recruiter/logout")

        response = await client.post("/auth/recruiter/login", json=recruiter_credentials())

    assert response.status_code == 200


async def test_wrong_password_and_unknown_email_fail_identically(app):
    """Distinguishing them turns the form into an account-enumeration oracle."""
    async with _client(app) as client:
        await client.post("/auth/recruiter/signup", json=recruiter_credentials())

        wrong_password = await client.post(
            "/auth/recruiter/login",
            json={"email": TEST_RECRUITER_EMAIL, "password": "not-the-password"},
        )
        unknown_email = await client.post(
            "/auth/recruiter/login",
            json={"email": "nobody@intermind.test", "password": TEST_RECRUITER_PASSWORD},
        )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


async def test_login_is_refused_when_no_account_exists(app):
    async with _client(app) as client:
        response = await client.post("/auth/recruiter/login", json=recruiter_credentials())

    assert response.status_code == 401


# --- sessions -----------------------------------------------------------------------------


async def test_the_session_cookie_is_httponly_and_samesite_strict(app):
    async with _client(app) as client:
        response = await client.post("/auth/recruiter/signup", json=recruiter_credentials())

    header = response.headers["set-cookie"].lower()
    assert "httponly" in header
    assert "samesite=strict" in header
    assert "path=/" in header


async def test_the_session_identifies_the_recruiter_it_was_issued_for(app):
    """Ownership reads `recruiter_id` off the session. It has to actually be there."""
    async with _client(app) as client:
        await client.post("/auth/recruiter/signup", json=recruiter_credentials())
        token = client.cookies[RECRUITER_SESSION_COOKIE]

    store: RecruiterSessionStore = app.state.recruiter_session_store
    stored = await app.state.recruiter_repository.get_by_email(TEST_RECRUITER_EMAIL)
    assert store.resolve(token).recruiter_id == stored.id


async def test_no_session_is_rejected(app):
    async with _client(app) as client:
        assert (await client.get(RECRUITER_ENDPOINT)).status_code == 401


async def test_an_unknown_session_value_is_rejected(app):
    async with _client(app) as client:
        client.cookies.set(RECRUITER_SESSION_COOKIE, "not-a-real-session-token")
        assert (await client.get(RECRUITER_ENDPOINT)).status_code == 401


async def test_an_expired_session_is_rejected(app):
    store: RecruiterSessionStore = app.state.recruiter_session_store
    expired = RecruiterSession(
        token="expired-session-token",
        recruiter_id="whoever",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    store._sessions[expired.token] = expired

    async with _client(app) as client:
        client.cookies.set(RECRUITER_SESSION_COOKIE, expired.token)
        assert (await client.get(RECRUITER_ENDPOINT)).status_code == 401

    assert store.active_count == 0


async def test_logout_revokes_the_session_server_side(app):
    store: RecruiterSessionStore = app.state.recruiter_session_store

    async with _client(app) as client:
        await client.post("/auth/recruiter/signup", json=recruiter_credentials())
        token = client.cookies[RECRUITER_SESSION_COOKIE]
        assert (await client.get(RECRUITER_ENDPOINT)).status_code == 200

        await client.post("/auth/recruiter/logout")
        assert store.active_count == 0

        # Replaying the cookie must not work - clearing it in the browser is not enough.
        client.cookies.set(RECRUITER_SESSION_COOKIE, token)
        assert (await client.get(RECRUITER_ENDPOINT)).status_code == 401


async def test_session_status_reports_whether_this_browser_is_signed_in(app):
    async with _client(app) as anonymous:
        assert (await anonymous.get("/auth/recruiter/session")).json()["authenticated"] is False

    async with _client(app) as client:
        await client.post("/auth/recruiter/signup", json=recruiter_credentials())
        assert (await client.get("/auth/recruiter/session")).json()["authenticated"] is True


# --- the candidate boundary -----------------------------------------------------------------


async def _start_interview(app) -> tuple[str, str]:
    async with _client(app) as recruiter:
        await recruiter.post("/auth/recruiter/signup", json=recruiter_credentials())
        job_id = (await recruiter.post("/jobs", json={"job_description": JD})).json()["id"]
        await recruiter.post(f"/jobs/{job_id}/interview-plan")
        started = (await recruiter.post("/interviews", json={"job_id": job_id})).json()
    return started["interview_id"], started["candidate_access_token"]


async def test_a_candidate_token_cannot_reach_a_recruiter_endpoint(app):
    _, candidate_token = await _start_interview(app)

    async with _client(app, candidate_token) as candidate:
        assert (await candidate.get(RECRUITER_ENDPOINT)).status_code == 401


async def test_a_candidate_token_cannot_be_used_as_a_session_cookie(app):
    """Two credential types, two stores. A candidate token is not a session."""
    _, candidate_token = await _start_interview(app)

    async with _client(app) as client:
        client.cookies.set(RECRUITER_SESSION_COOKIE, candidate_token)
        assert (await client.get(RECRUITER_ENDPOINT)).status_code == 401


async def test_a_candidate_token_still_reaches_its_own_interview(app):
    """Candidate authentication is untouched by recruiter accounts existing."""
    interview_id, candidate_token = await _start_interview(app)

    async with _client(app, candidate_token) as candidate:
        assert (await candidate.get(f"/interviews/{interview_id}")).status_code == 200


async def test_a_recruiter_session_still_reaches_a_candidate_interview_endpoint(app):
    """Pre-existing, deliberate and one-directional - unchanged by this milestone."""
    interview_id, _ = await _start_interview(app)

    async with _client(app) as client:
        await client.post(
            "/auth/recruiter/login", json=recruiter_credentials()
        )
        assert (await client.get(f"/interviews/{interview_id}")).status_code == 200


async def test_a_recruiter_session_token_is_not_an_interview_access_token(app):
    """The session must not leak into the candidate credential space."""
    interview_id, _ = await _start_interview(app)
    store: RecruiterSessionStore = app.state.recruiter_session_store
    session = store.create("some-recruiter")

    async with _client(app, session.token) as impostor:
        assert (await impostor.get(f"/interviews/{interview_id}")).status_code == 401
