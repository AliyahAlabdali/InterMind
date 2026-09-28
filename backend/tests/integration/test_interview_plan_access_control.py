"""Access control for a job's interview plan.

The plan is the recruiter's assessment strategy for a role: every competency, technology and
task the interview may probe, each with its requirement level, priority, provenance and O*NET
grounding. Both plan endpoints were public until the multi-recruiter audit, which was harmless
with one configured account and, with accounts, meant a job id alone was enough to

* read another recruiter's assessment strategy, and
* generate a plan on another recruiter's job, unauthenticated.

Every other recruiter-owned route had already been scoped through ``get_for_recruiter`` when the
product grew accounts; these two were left behind. This module is the boundary they now hold.

Conventions inherited from ``test_tenant_isolation``: another tenant's resource is **404**, not
403, so a probe cannot confirm it exists; a missing credential is **401**.
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

#: Fields of the full plan that the candidate shape must never carry. Each is either the
#: recruiter's weighting of a target or the O*NET reasoning behind choosing it.
RECRUITER_ONLY_PLAN_FIELDS = (
    "competencies",
    "technologies",
    "tasks",
    "occupation_match",
    "alternate_matches",
    "onet_context",
    "onet_grounding_used",
    "seniority",
)


@pytest.fixture(autouse=True)
def _use_fixture_kb(app):
    app.dependency_overrides[get_onet_kb] = lambda: OnetKnowledgeBase(path=FIXTURE_KB_PATH)


@dataclass
class Tenant:
    client: AsyncClient
    job_id: str
    interview_id: str
    candidate_token: str


async def _make_tenant(app, email: str, jd: str) -> Tenant:
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    signup = await client.post("/auth/recruiter/signup", json=recruiter_credentials(email))
    assert signup.status_code == 201, signup.text

    job_id = (await client.post("/jobs", json={"job_description": jd})).json()["id"]
    plan = await client.post(f"/jobs/{job_id}/interview-plan")
    assert plan.status_code == 201, plan.text
    started = (await client.post("/interviews", json={"job_id": job_id})).json()
    return Tenant(
        client=client,
        job_id=job_id,
        interview_id=started["interview_id"],
        candidate_token=started["candidate_access_token"],
    )


@pytest.fixture
async def tenants(app):
    a = await _make_tenant(app, "plan-a@intermind.test", JD_A)
    b = await _make_tenant(app, "plan-b@intermind.test", JD_B)
    yield a, b
    await a.client.aclose()
    await b.client.aclose()


@pytest.fixture
async def anonymous(app):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield client
    await client.aclose()


# --- the owner --------------------------------------------------------------------------------


async def test_the_owning_recruiter_reads_the_whole_plan(tenants):
    a, _ = tenants

    response = await a.client.get(f"/jobs/{a.job_id}/interview-plan")

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == a.job_id
    assert body["coverage_targets"], "the owner's plan should carry its targets"
    # The strategy fields are the point of the recruiter view; they must still be there.
    for field in RECRUITER_ONLY_PLAN_FIELDS:
        assert field in body, f"the owner's plan lost {field}"


async def test_the_owning_recruiter_can_plan_their_own_job(tenants):
    """And the endpoint stays idempotent: a repeat call returns the same plan with 200."""
    a, _ = tenants

    repeat = await a.client.post(f"/jobs/{a.job_id}/interview-plan")

    assert repeat.status_code == 200
    assert repeat.json()["job_id"] == a.job_id


# --- cross-tenant -----------------------------------------------------------------------------


async def test_a_recruiter_cannot_read_the_others_plan(tenants):
    a, b = tenants

    assert (await b.client.get(f"/jobs/{a.job_id}/interview-plan")).status_code == 404
    assert (await a.client.get(f"/jobs/{b.job_id}/interview-plan")).status_code == 404


async def test_a_recruiter_cannot_plan_the_others_job(tenants):
    a, b = tenants

    response = await b.client.post(f"/jobs/{a.job_id}/interview-plan")

    assert response.status_code == 404
    # ...and A's own plan is untouched and still readable by A.
    assert (await a.client.get(f"/jobs/{a.job_id}/interview-plan")).status_code == 200


async def test_the_others_plan_is_not_found_rather_than_forbidden(tenants):
    """404 and not 403: a 403 would confirm the job exists and is simply someone else's."""
    a, b = tenants

    real_but_not_mine = await b.client.get(f"/jobs/{a.job_id}/interview-plan")
    pure_fiction = await b.client.get("/jobs/0123456789abcdef0123456789abcdef/interview-plan")

    assert real_but_not_mine.status_code == pure_fiction.status_code == 404


# --- unauthenticated --------------------------------------------------------------------------


async def test_reading_a_plan_requires_a_credential(tenants, anonymous):
    a, _ = tenants

    assert (await anonymous.get(f"/jobs/{a.job_id}/interview-plan")).status_code == 401


async def test_creating_a_plan_requires_a_recruiter_session(tenants, anonymous):
    """The state-changing half. Unauthenticated, this used to create a plan on someone's job."""
    a, _ = tenants

    response = await anonymous.post(f"/jobs/{a.job_id}/interview-plan")

    assert response.status_code == 401


async def test_an_unknown_job_is_indistinguishable_to_an_anonymous_caller(tenants, anonymous):
    a, _ = tenants

    real = await anonymous.get(f"/jobs/{a.job_id}/interview-plan")
    fictional = await anonymous.get("/jobs/0123456789abcdef0123456789abcdef/interview-plan")

    assert real.status_code == fictional.status_code == 401


# --- the candidate ----------------------------------------------------------------------------


async def test_a_candidate_reads_the_reduced_plan_for_their_own_interview(tenants, anonymous):
    """The candidate interview screen needs the role name, the target count and the target
    names (the last to bias speech recognition). It gets those and nothing else."""
    a, _ = tenants

    response = await anonymous.get(
        f"/jobs/{a.job_id}/interview-plan",
        headers={"Authorization": f"Bearer {a.candidate_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"job_id", "role_title", "coverage_targets"}
    assert body["role_title"]
    assert body["coverage_targets"], "the progress rail needs the targets"
    for target in body["coverage_targets"]:
        assert set(target) == {"id", "target"}
    for field in RECRUITER_ONLY_PLAN_FIELDS:
        assert field not in body, f"the candidate shape leaked {field}"


async def test_a_candidate_token_does_not_open_another_jobs_plan(tenants, anonymous):
    """The token is matched against this job's own interviews, so it is not a master key."""
    a, b = tenants

    response = await anonymous.get(
        f"/jobs/{b.job_id}/interview-plan",
        headers={"Authorization": f"Bearer {a.candidate_token}"},
    )

    assert response.status_code == 401


async def test_a_made_up_bearer_token_is_rejected(tenants, anonymous):
    a, _ = tenants

    response = await anonymous.get(
        f"/jobs/{a.job_id}/interview-plan",
        headers={"Authorization": "Bearer not-a-real-access-token"},
    )

    assert response.status_code == 401


async def test_the_candidate_interview_flow_still_works_end_to_end(tenants, anonymous):
    """The regression this fix had to avoid: the interview screen reads the plan on every load,
    so scoping the endpoint must not lock the candidate out of their own interview."""
    a, _ = tenants
    headers = {"Authorization": f"Bearer {a.candidate_token}"}

    interview = await anonymous.get(f"/interviews/{a.interview_id}", headers=headers)
    job = await anonymous.get(f"/jobs/{a.job_id}")
    plan = await anonymous.get(f"/jobs/{a.job_id}/interview-plan", headers=headers)
    answer = await anonymous.post(
        f"/interviews/{a.interview_id}/answers",
        json={"answer": "I built a Python service and versioned every schema migration."},
        headers=headers,
    )

    assert interview.status_code == 200
    assert job.status_code == 200
    assert plan.status_code == 200
    assert answer.status_code == 200
    assert interview.json()["current_question_text"]


# --- the public job endpoint, unchanged ---------------------------------------------------------


async def test_the_reduced_job_endpoint_stays_public(tenants, anonymous):
    """Deliberately open: the candidate's screen names the role before any token exists, and a
    candidate holds only their own interview's token. Pinned so it is not closed by accident."""
    a, _ = tenants

    response = await anonymous.get(f"/jobs/{a.job_id}")

    assert response.status_code == 200
    assert response.json()["job_spec"]["role_title"]


async def test_the_public_job_endpoint_withholds_the_job_description(tenants, anonymous):
    """The raw job-description text is the recruiter's own content and is not rendered anywhere
    in the product. It must not come back on an endpoint that needs no credential."""
    a, _ = tenants

    body = (await anonymous.get(f"/jobs/{a.job_id}")).json()

    assert set(body) == {"id", "job_spec", "created_at"}
    assert "job_description" not in body
    assert "recruiter_id" not in body
