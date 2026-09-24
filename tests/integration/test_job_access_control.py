"""Regression tests: job creation and listing are recruiter-only.

A QA pass found ``POST /jobs`` answering unauthenticated requests with 201 - an unauthenticated
write that also spends an LLM call on job-description analysis - and ``GET /jobs`` returning
every role in the deployment, with its full description, to anyone who asked.

``GET /jobs/{job_id}`` is deliberately *not* included in that change and is pinned here as
public: the candidate's interview screen reads it to name the role being interviewed for, and a
candidate holds only their own interview's token. See ``app/api/routes/jobs.py``.

Builds its own clients rather than using the shared ``client`` fixture, which carries a
recruiter credential by default (see ``tests/conftest.py``) - these tests need to control which
credential, if any, is presented.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_onet_kb
from app.knowledge.onet_kb import OnetKnowledgeBase
from tests.conftest import FIXTURES, recruiter_credentials

FIXTURE_KB_PATH = FIXTURES / "onet_kb_fixture.jsonl"

JD = "Backend Software Engineer\nPython and Git experience required. Critical thinking a must."


@pytest.fixture(autouse=True)
def _use_fixture_kb(app):
    app.dependency_overrides[get_onet_kb] = lambda: OnetKnowledgeBase(path=FIXTURE_KB_PATH)


def _client(app, token: str | None = None) -> AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers)


@asynccontextmanager
async def _recruiter_client(app):
    """A client signed in as the configured recruiter, holding its session cookie.

    Registers the account and keeps its session cookie. Recruiters are persistent rows now, so
    a test that needs one creates it the same way a person would.

    A context manager rather than a plain factory: httpx refuses to re-enter a client that has
    already issued a request, and signing in is a request.
    """
    async with _client(app) as client:
        response = await client.post("/auth/recruiter/signup", json=recruiter_credentials())
        assert response.status_code == 201, f"recruiter signup failed: {response.text}"
        yield client


async def _candidate_token(app) -> str:
    """Start a real interview and return its own candidate access token."""
    async with _recruiter_client(app) as recruiter:
        job_id = (await recruiter.post("/jobs", json={"job_description": JD})).json()["id"]
        await recruiter.post(f"/jobs/{job_id}/interview-plan")
        started = await recruiter.post("/interviews", json={"job_id": job_id})
        return started.json()["candidate_access_token"]


# --- POST /jobs -------------------------------------------------------------------------


async def test_creating_a_job_without_a_credential_is_rejected(app):
    async with _client(app) as anonymous:
        response = await anonymous.post("/jobs", json={"job_description": JD})

    assert response.status_code == 401


async def test_creating_a_job_with_a_recruiter_credential_is_allowed(app):
    async with _recruiter_client(app) as recruiter:
        response = await recruiter.post("/jobs", json={"job_description": JD})

    assert response.status_code == 201
    assert response.json()["job_description"] == JD


async def test_creating_a_job_with_a_candidate_token_is_rejected(app):
    """A candidate's own interview token is not a recruiter credential, and must not act as
    one outside that interview."""
    token = await _candidate_token(app)

    async with _client(app, token) as candidate:
        response = await candidate.post("/jobs", json={"job_description": JD})

    assert response.status_code == 401


async def test_a_rejected_job_creation_stores_nothing(app):
    """The point of guarding a write: the refusal has to happen before the work."""
    async with _client(app) as anonymous:
        await anonymous.post("/jobs", json={"job_description": "should never be stored"})

    async with _recruiter_client(app) as recruiter:
        jobs = (await recruiter.get("/jobs")).json()

    assert all(job["job_description"] != "should never be stored" for job in jobs)


# --- GET /jobs --------------------------------------------------------------------------


async def test_listing_jobs_without_a_credential_is_rejected(app):
    async with _client(app) as anonymous:
        response = await anonymous.get("/jobs")

    assert response.status_code == 401


async def test_listing_jobs_with_a_recruiter_credential_is_allowed(app):
    async with _recruiter_client(app) as recruiter:
        await recruiter.post("/jobs", json={"job_description": JD})
        response = await recruiter.get("/jobs")

    assert response.status_code == 200
    assert len(response.json()) >= 1


async def test_listing_jobs_with_a_candidate_token_is_rejected(app):
    token = await _candidate_token(app)

    async with _client(app, token) as candidate:
        response = await candidate.get("/jobs")

    assert response.status_code == 401


# --- GET /jobs/{job_id} stays public ----------------------------------------------------


async def test_reading_one_job_stays_public_for_the_candidate_screen(app):
    """Pinned deliberately. The candidate interview needs the role's title and holds no
    recruiter credential; narrowing this is a per-interview/per-job scoping change, not part of
    closing the unauthenticated-write hole."""
    async with _recruiter_client(app) as recruiter:
        job_id = (await recruiter.post("/jobs", json={"job_description": JD})).json()["id"]

    async with _client(app) as anonymous:
        response = await anonymous.get(f"/jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["id"] == job_id


async def test_the_candidate_entry_flow_still_works_end_to_end(app):
    """The whole point of leaving that route alone: a candidate with only their own token can
    still load everything their interview screen needs."""
    async with _recruiter_client(app) as recruiter:
        job_id = (await recruiter.post("/jobs", json={"job_description": JD})).json()["id"]
        await recruiter.post(f"/jobs/{job_id}/interview-plan")
        started = (await recruiter.post("/interviews", json={"job_id": job_id})).json()

    interview_id = started["interview_id"]
    async with _client(app, started["candidate_access_token"]) as candidate:
        interview = await candidate.get(f"/interviews/{interview_id}")
        job = await candidate.get(f"/jobs/{job_id}")
        plan = await candidate.get(f"/jobs/{job_id}/interview-plan")

    assert interview.status_code == 200
    assert job.status_code == 200
    assert plan.status_code == 200
    assert interview.json()["current_question_text"]
