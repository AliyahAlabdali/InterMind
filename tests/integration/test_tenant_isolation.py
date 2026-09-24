"""Tenant isolation: Recruiter A must never reach Recruiter B's data.

The security property the multi-recruiter milestone exists to guarantee. Two recruiters register
independently, each creates their own job and interview, and every recruiter-private resource is
probed from both directions.

Two conventions under test throughout:

* **Ownership is server-side.** It comes from the session, never from a request body. The
  creation tests below try to name an owner and are ignored.
* **Another recruiter's resource is indistinguishable from one that does not exist** - 404, not
  403. A 403 would confirm the resource exists, which is enough to enumerate a competitor's job
  ids and learn how many candidates they are interviewing.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_onet_kb
from app.knowledge.onet_kb import OnetKnowledgeBase
from tests.conftest import FIXTURES, recruiter_credentials

FIXTURE_KB_PATH = FIXTURES / "onet_kb_fixture.jsonl"
JD_A = "Backend Software Engineer\nPython and Git experience required. Critical thinking a must."
JD_B = "Data Engineer\nPython and SQL experience required. Attention to detail a must."


@pytest.fixture(autouse=True)
def _use_fixture_kb(app):
    app.dependency_overrides[get_onet_kb] = lambda: OnetKnowledgeBase(path=FIXTURE_KB_PATH)


@dataclass
class Tenant:
    """One recruiter, signed in, with a job and an interview of their own."""

    client: AsyncClient
    email: str
    job_id: str
    interview_id: str
    candidate_token: str


async def _make_tenant(app, email: str, jd: str) -> Tenant:
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    signup = await client.post("/auth/recruiter/signup", json=recruiter_credentials(email))
    assert signup.status_code == 201, signup.text

    job_id = (await client.post("/jobs", json={"job_description": jd})).json()["id"]
    await client.post(f"/jobs/{job_id}/interview-plan")
    started = (await client.post("/interviews", json={"job_id": job_id})).json()
    return Tenant(
        client=client,
        email=email,
        job_id=job_id,
        interview_id=started["interview_id"],
        candidate_token=started["candidate_access_token"],
    )


@pytest.fixture
async def tenants(app):
    """Recruiter A and Recruiter B, each with their own job and interview."""
    a = await _make_tenant(app, "a@intermind.test", JD_A)
    b = await _make_tenant(app, "b@intermind.test", JD_B)
    yield a, b
    await a.client.aclose()
    await b.client.aclose()


# --- listing: each recruiter sees only their own -------------------------------------------


async def test_each_recruiter_lists_only_their_own_jobs(tenants):
    a, b = tenants

    a_jobs = {job["id"] for job in (await a.client.get("/jobs")).json()}
    b_jobs = {job["id"] for job in (await b.client.get("/jobs")).json()}

    assert a_jobs == {a.job_id}
    assert b_jobs == {b.job_id}
    assert a_jobs.isdisjoint(b_jobs)


async def test_the_activity_feed_shows_only_the_recruiters_own_interviews(tenants):
    a, b = tenants
    # Give both feeds something to carry.
    await a.client.post(
        f"/interviews/{a.interview_id}/answers",
        json={"answer": "I built a Python service and versioned every schema migration."},
        headers={"Authorization": f"Bearer {a.candidate_token}"},
    )
    await b.client.post(
        f"/interviews/{b.interview_id}/answers",
        json={"answer": "I built SQL pipelines and tuned the slow queries."},
        headers={"Authorization": f"Bearer {b.candidate_token}"},
    )

    a_feed = (await a.client.get("/activity")).json()
    b_feed = (await b.client.get("/activity")).json()

    assert a_feed, "A's own activity should be visible to A"
    assert all(event["job_id"] == a.job_id for event in a_feed)
    assert all(event["job_id"] == b.job_id for event in b_feed)


# --- direct object references ---------------------------------------------------------------


async def test_a_recruiter_cannot_read_the_others_job_listing(tenants):
    a, b = tenants

    assert (await a.client.get(f"/jobs/{b.job_id}/interviews")).status_code == 404
    assert (await b.client.get(f"/jobs/{a.job_id}/interviews")).status_code == 404
    # ...while each can read their own.
    assert (await a.client.get(f"/jobs/{a.job_id}/interviews")).status_code == 200
    assert (await b.client.get(f"/jobs/{b.job_id}/interviews")).status_code == 200


async def test_a_recruiter_cannot_read_the_others_report(tenants):
    """The endpoint carrying scores, evidence and candidate quotes."""
    a, b = tenants

    assert (await a.client.get(f"/interviews/{b.interview_id}/report")).status_code == 404
    assert (await b.client.get(f"/interviews/{a.interview_id}/report")).status_code == 404


async def test_a_recruiter_cannot_start_an_interview_against_the_others_job(tenants):
    """Otherwise a known job id is enough to put candidates into someone else's pipeline."""
    a, b = tenants

    response = await a.client.post("/interviews", json={"job_id": b.job_id})

    assert response.status_code == 404
    # ...and nothing was created.
    assert len((await b.client.get(f"/jobs/{b.job_id}/interviews")).json()) == 1


async def test_a_recruiter_cannot_read_the_others_candidate_interview(tenants):
    """The recruiter override on candidate endpoints, scoped.

    `require_candidate_access` lets a recruiter see what their candidate sees. That override
    used to accept *any* recruiter, which was correct when there was one - and with two meant
    Recruiter B could read Recruiter A's interview: the candidate's name, email, every question
    and every answer. Found in the multi-tenant audit; this pins it shut.
    """
    a, b = tenants

    assert (await b.client.get(f"/interviews/{a.interview_id}")).status_code == 404
    assert (await a.client.get(f"/interviews/{b.interview_id}")).status_code == 404
    # The intended behaviour survives: each still reaches their own candidate's interview.
    assert (await a.client.get(f"/interviews/{a.interview_id}")).status_code == 200
    assert (await b.client.get(f"/interviews/{b.interview_id}")).status_code == 200


async def test_a_recruiter_cannot_answer_into_the_others_interview(tenants):
    a, b = tenants

    response = await b.client.post(
        f"/interviews/{a.interview_id}/answers", json={"answer": "not mine to give"}
    )

    assert response.status_code == 404


async def test_a_recruiter_cannot_mint_a_speech_token_for_the_others_interview(tenants):
    a, b = tenants

    assert (
        await b.client.get(f"/interviews/{a.interview_id}/speech-token")
    ).status_code in (404, 500)  # 500 only when speech is unconfigured; never 200


async def test_another_recruiters_resource_is_not_found_rather_than_forbidden(tenants):
    """404 and not 403: a 403 confirms the resource exists."""
    a, b = tenants

    real_but_not_mine = await a.client.get(f"/jobs/{b.job_id}/interviews")
    pure_fiction = await a.client.get("/jobs/0123456789abcdef0123456789abcdef/interviews")

    assert real_but_not_mine.status_code == pure_fiction.status_code == 404


# --- the client never chooses the owner ------------------------------------------------------


async def test_a_created_job_is_owned_by_the_session_that_created_it(app, tenants):
    a, _ = tenants

    created = await a.client.post("/jobs", json={"job_description": JD_A})
    job_id = created.json()["id"]

    stored = await app.state.job_repository.get(job_id)
    recruiter = await app.state.recruiter_repository.get_by_email(a.email)
    assert stored.recruiter_id == recruiter.id


async def test_a_recruiter_cannot_claim_ownership_through_the_request_body(app, tenants):
    """The payload has no owner field, and smuggling one in changes nothing."""
    a, b = tenants
    b_recruiter = await app.state.recruiter_repository.get_by_email(b.email)

    created = await a.client.post(
        "/jobs",
        json={"job_description": JD_A, "recruiter_id": b_recruiter.id, "owner": b_recruiter.id},
    )
    assert created.status_code == 201

    stored = await app.state.job_repository.get(created.json()["id"])
    a_recruiter = await app.state.recruiter_repository.get_by_email(a.email)
    assert stored.recruiter_id == a_recruiter.id
    # ...and it did not appear in B's workspace.
    assert created.json()["id"] not in {job["id"] for job in (await b.client.get("/jobs")).json()}


async def test_the_owning_recruiter_id_is_never_returned_to_a_client(tenants):
    a, _ = tenants

    listing = (await a.client.get("/jobs")).json()
    public = (await a.client.get(f"/jobs/{a.job_id}")).json()

    assert all("recruiter_id" not in job for job in listing)
    assert "recruiter_id" not in public


# --- the candidate boundary is unaffected ----------------------------------------------------


async def test_a_candidate_reaches_their_own_interview_without_any_recruiter_account(app, tenants):
    a, _ = tenants

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {a.candidate_token}"},
    ) as candidate:
        assert (await candidate.get(f"/interviews/{a.interview_id}")).status_code == 200


async def test_a_candidate_cannot_reach_another_recruiters_interview(app, tenants):
    a, b = tenants

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {a.candidate_token}"},
    ) as candidate_a:
        assert (await candidate_a.get(f"/interviews/{b.interview_id}")).status_code == 401


async def test_a_candidate_cannot_reach_recruiter_endpoints_of_either_tenant(app, tenants):
    a, b = tenants

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {a.candidate_token}"},
    ) as candidate_a:
        assert (await candidate_a.get("/jobs")).status_code == 401
        assert (await candidate_a.get("/activity")).status_code == 401
        assert (
            await candidate_a.get(f"/interviews/{a.interview_id}/report")
        ).status_code == 401
        assert (await candidate_a.get(f"/jobs/{b.job_id}/interviews")).status_code == 401


async def test_the_public_job_endpoint_exposes_no_recruiter_private_content(app, tenants):
    """It stays public for the candidate's interview screen, so it must carry nothing private."""
    a, _ = tenants

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        public = await anon.get(f"/jobs/{a.job_id}")

    assert public.status_code == 200
    body = public.json()
    assert "job_description" not in body  # the recruiter's raw JD text
    assert "recruiter_id" not in body
    assert set(body) == {"id", "job_spec", "created_at"}
