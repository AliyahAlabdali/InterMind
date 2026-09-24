"""Regression tests for the Milestone 4 recruiter/candidate access boundary (``app.api.auth``).

Confirms the boundary is a real, enforced HTTP-layer check - not just "the candidate frontend
never calls that endpoint" - which is what Copilot's M4-closing review flagged: with only an
interview id (no additional credential), anyone could previously call
``GET /interviews/{id}/report`` or ``GET /jobs/{job_id}/interviews`` and read recruiter-only
evaluation data (scores/evidence/weaknesses) or another candidate's session list.

Uses its own unauthenticated/candidate-scoped ``httpx.AsyncClient`` instances (via the ``app``
fixture from ``tests/conftest.py``) rather than the shared ``client`` fixture, which carries a
valid recruiter credential by default - that default is what keeps the rest of the existing
test suite passing unchanged (see ``tests/conftest.py``), but these tests specifically need to
control which credential (if any) is presented.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_onet_kb
from app.knowledge.onet_kb import OnetKnowledgeBase
from tests.conftest import FIXTURES, recruiter_credentials

FIXTURE_KB_PATH = FIXTURES / "onet_kb_fixture.jsonl"


DETAILED_ANSWER = (
    "I led a project where I diagnosed a race condition in a queue consumer, wrote a "
    "regression test to reproduce it, fixed the underlying lock ordering, and verified it "
    "in staging before shipping."
)
SHORT_ANSWER = "I did that once."


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


async def _create_job_with_plan(recruiter: AsyncClient) -> tuple[str, list[str]]:
    jd = "Backend Software Engineer\nPython and Git experience required. Critical thinking a must."
    job_resp = await recruiter.post("/jobs", json={"job_description": jd})
    job_id = job_resp.json()["id"]
    plan_resp = await recruiter.post(f"/jobs/{job_id}/interview-plan")
    question_ids = [t["id"] for t in plan_resp.json()["coverage_targets"]]
    return job_id, question_ids


async def _start_interview(
    recruiter: AsyncClient, job_id: str, name: str = "Candidate", email: str = ""
) -> tuple[str, str]:
    resp = await recruiter.post(
        "/interviews", json={"job_id": job_id, "candidate_name": name, "candidate_email": email}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["candidate_access_token"], "expected POST /interviews to mint a candidate token"
    return body["interview_id"], body["candidate_access_token"]


async def _complete_interview(client: AsyncClient, interview_id: str, num_questions: int) -> None:
    for _ in range(num_questions):
        resp = await client.post(
            f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER}
        )
        assert resp.status_code == 200, resp.text
    assert resp.json()["finished"] is True


# --- A: candidate access can access its own interview/question flow ------------------------


async def test_A_candidate_token_can_access_its_own_interview_flow(app):
    async with _recruiter_client(app) as recruiter:
        job_id, questions = await _create_job_with_plan(recruiter)
        interview_id, candidate_token = await _start_interview(recruiter, job_id)

    async with _client(app, candidate_token) as candidate:
        get_resp = await candidate.get(f"/interviews/{interview_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["interview_id"] == interview_id

        answer_resp = await candidate.post(
            f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER}
        )
        assert answer_resp.status_code == 200
        assert answer_resp.json()["current_question_id"] == questions[1]


# --- B: candidate access cannot access recruiter report -------------------------------------


async def test_B_candidate_token_cannot_access_recruiter_report(app):
    async with _recruiter_client(app) as recruiter:
        job_id, _ = await _create_job_with_plan(recruiter)
        interview_id, candidate_token = await _start_interview(recruiter, job_id)

    async with _client(app, candidate_token) as candidate:
        resp = await candidate.get(f"/interviews/{interview_id}/report")
        assert resp.status_code == 401
        assert "score" not in resp.text.lower()
        assert "evidence" not in resp.text.lower()
        assert "weakness" not in resp.text.lower()


# --- C: candidate access cannot access recruiter interview/candidate listing ----------------


async def test_C_candidate_token_cannot_access_recruiter_candidate_listing(app):
    async with _recruiter_client(app) as recruiter:
        job_id, _ = await _create_job_with_plan(recruiter)
        _, candidate_token = await _start_interview(recruiter, job_id)

    async with _client(app, candidate_token) as candidate:
        resp = await candidate.get(f"/jobs/{job_id}/interviews")
        assert resp.status_code == 401


# --- D/E: recruiter access can reach recruiter report + candidate listing -------------------


async def test_D_recruiter_access_can_access_recruiter_report(app):
    async with _recruiter_client(app) as recruiter:
        job_id, questions = await _create_job_with_plan(recruiter)
        interview_id, _ = await _start_interview(recruiter, job_id)
        await _complete_interview(recruiter, interview_id, len(questions))

        resp = await recruiter.get(f"/interviews/{interview_id}/report")
        assert resp.status_code == 200
        body = resp.json()
        assert "overall_score" in body
        assert "question_evaluations" in body


async def test_E_recruiter_access_can_access_recruiter_candidate_listing(app):
    async with _recruiter_client(app) as recruiter:
        job_id, _ = await _create_job_with_plan(recruiter)
        interview_id, _ = await _start_interview(recruiter, job_id, name="Ada Lovelace")

        resp = await recruiter.get(f"/jobs/{job_id}/interviews")
        assert resp.status_code == 200
        summaries = resp.json()
        assert any(s["interview_id"] == interview_id for s in summaries)
        assert any(s["candidate_name"] == "Ada Lovelace" for s in summaries)


# --- F: invalid/missing access is rejected ---------------------------------------------------


async def test_F_missing_or_invalid_credential_is_rejected(app):
    async with _recruiter_client(app) as recruiter:
        job_id, _ = await _create_job_with_plan(recruiter)
        interview_id, candidate_token = await _start_interview(recruiter, job_id)

    # No credential at all.
    async with _client(app, None) as anon:
        assert (await anon.get(f"/interviews/{interview_id}")).status_code == 401
        assert (await anon.get(f"/interviews/{interview_id}/report")).status_code == 401
        assert (await anon.get(f"/jobs/{job_id}/interviews")).status_code == 401
        assert (
            await anon.post("/interviews", json={"job_id": job_id})
        ).status_code == 401

    # A garbage token, not a prefix/suffix of anything real.
    async with _client(app, "not-a-real-token") as bogus:
        assert (await bogus.get(f"/interviews/{interview_id}")).status_code == 401
        assert (await bogus.get(f"/interviews/{interview_id}/report")).status_code == 401

    # A candidate token used against the *recruiter-only* endpoints is also invalid there.
    async with _client(app, candidate_token) as candidate:
        assert (await candidate.get(f"/interviews/{interview_id}/report")).status_code == 401


# --- G: an interview's access token cannot be used to access a different interview ----------


async def test_G_interview_a_token_cannot_access_interview_b(app):
    async with _recruiter_client(app) as recruiter:
        job_id, _ = await _create_job_with_plan(recruiter)
        interview_a, token_a = await _start_interview(
            recruiter, job_id, name="Alice", email="a@x.com"
        )
        interview_b, token_b = await _start_interview(
            recruiter, job_id, name="Bob", email="b@x.com"
        )
    assert token_a != token_b
    assert interview_a != interview_b

    async with _client(app, token_a) as candidate_a:
        own_resp = await candidate_a.get(f"/interviews/{interview_a}")
        assert own_resp.status_code == 200

        other_resp = await candidate_a.get(f"/interviews/{interview_b}")
        assert other_resp.status_code == 401

        other_answer_resp = await candidate_a.post(
            f"/interviews/{interview_b}/answers", json={"answer": DETAILED_ANSWER}
        )
        assert other_answer_resp.status_code == 401


# --- H: existing interview functionality still works (using the default recruiter-credentialed
# --- `client` fixture, exactly like every other integration test) --------------------------


async def test_H_existing_interview_functionality_still_works(client):
    job_id, questions = await _create_job_with_plan(client)
    interview_id, _ = await _start_interview(client, job_id)

    await _complete_interview(client, interview_id, len(questions))

    report = await client.get(f"/interviews/{interview_id}/report")
    assert report.status_code == 200

    listing = await client.get(f"/jobs/{job_id}/interviews")
    assert listing.status_code == 200
    assert any(s["interview_id"] == interview_id for s in listing.json())


# --- I: existing follow-up behavior remains unchanged ----------------------------------------


async def test_I_follow_up_behavior_remains_unchanged(client):
    job_id, questions = await _create_job_with_plan(client)
    interview_id, _ = await _start_interview(client, job_id)

    follow_up = await client.post(
        f"/interviews/{interview_id}/answers", json={"answer": SHORT_ANSWER}
    )
    assert follow_up.status_code == 200
    follow_up_body = follow_up.json()
    assert follow_up_body["current_question_id"] == questions[0]
    assert follow_up_body["current_question_is_follow_up"] is True

    advanced = await client.post(
        f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER}
    )
    assert advanced.status_code == 200
    advanced_body = advanced.json()
    assert advanced_body["current_question_is_follow_up"] is False
    assert advanced_body["current_question_id"] == questions[1]

    # The identity fix from the previous M4 pass still holds under the new access boundary:
    # the original and follow-up turns keep their own distinct ids in history.
    history = advanced_body["history"]
    assert len(history) == 2
    assert history[0]["question_id"] == questions[0]
    assert history[1]["question_id"] not in questions
