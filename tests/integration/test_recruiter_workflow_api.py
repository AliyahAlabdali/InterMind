"""Integration tests for the recruiter-workflow endpoints introduced alongside candidate
identity: `GET /jobs` (dashboard) and `GET /jobs/{job_id}/interviews` (candidate table).

See the recruiter-workflow architecture review: the recruiter dashboard must be backed by real
backend state (not client-side tracking), and candidate identity must be associated with the
correct interview/session, with recruiter-only fields never leaking to the candidate-facing
endpoints.
"""

from __future__ import annotations

import pytest

from app.api.deps import get_onet_kb
from app.knowledge.onet_kb import OnetKnowledgeBase
from tests.conftest import FIXTURES

FIXTURE_KB_PATH = FIXTURES / "onet_kb_fixture.jsonl"

DETAILED_ANSWER = (
    "I led a project where I diagnosed a race condition in a queue consumer, wrote a "
    "regression test to reproduce it, fixed the underlying lock ordering, and verified it "
    "in staging before shipping."
)


@pytest.fixture(autouse=True)
def _use_fixture_kb(app):
    app.dependency_overrides[get_onet_kb] = lambda: OnetKnowledgeBase(path=FIXTURE_KB_PATH)


async def _create_job_with_plan(client) -> tuple[str, list[str]]:
    jd = "Backend Software Engineer\nPython and Git experience required. Critical thinking a must."
    job_resp = await client.post("/jobs", json={"job_description": jd})
    job_id = job_resp.json()["id"]
    plan_resp = await client.post(f"/jobs/{job_id}/interview-plan")
    question_ids = [q["id"] for q in plan_resp.json()["questions"]]
    return job_id, question_ids


async def _start_candidate(client, job_id: str, name: str, email: str) -> str:
    resp = await client.post(
        "/interviews",
        json={"job_id": job_id, "candidate_name": name, "candidate_email": email},
    )
    assert resp.status_code == 201
    return resp.json()["interview_id"]


async def test_dashboard_lists_every_created_job(client):
    job_id_1, _ = await _create_job_with_plan(client)
    job_id_2, _ = await _create_job_with_plan(client)

    resp = await client.get("/jobs")
    assert resp.status_code == 200
    listed_ids = {job["id"] for job in resp.json()}
    assert {job_id_1, job_id_2} <= listed_ids


async def test_multiple_candidates_can_belong_to_the_same_interview(client):
    job_id, _ = await _create_job_with_plan(client)

    id_a = await _start_candidate(client, job_id, "Ahmed Ali", "ahmed@example.com")
    id_b = await _start_candidate(client, job_id, "Sara Mohammed", "sara@example.com")
    id_c = await _start_candidate(client, job_id, "Omar Hassan", "omar@example.com")

    resp = await client.get(f"/jobs/{job_id}/interviews")
    assert resp.status_code == 200
    body = resp.json()
    assert {c["interview_id"] for c in body} == {id_a, id_b, id_c}


async def test_candidate_data_is_associated_with_the_correct_session(client):
    job_id, _ = await _create_job_with_plan(client)
    id_a = await _start_candidate(client, job_id, "Ahmed Ali", "ahmed@example.com")
    id_b = await _start_candidate(client, job_id, "Sara Mohammed", "sara@example.com")

    body = (await client.get(f"/jobs/{job_id}/interviews")).json()
    by_id = {c["interview_id"]: c for c in body}

    assert by_id[id_a]["candidate_name"] == "Ahmed Ali"
    assert by_id[id_a]["candidate_email"] == "ahmed@example.com"
    assert by_id[id_b]["candidate_name"] == "Sara Mohammed"
    assert by_id[id_b]["candidate_email"] == "sara@example.com"

    # The candidate's own interview response also carries their own (not another
    # candidate's) name/email.
    own_view = (await client.get(f"/interviews/{id_a}")).json()
    assert own_view["candidate_name"] == "Ahmed Ali"
    assert own_view["candidate_email"] == "ahmed@example.com"


async def test_dashboard_shows_correct_status_counts(client):
    job_id, question_ids = await _create_job_with_plan(client)
    not_started_id = await _start_candidate(client, job_id, "Lina Saleh", "lina@example.com")
    in_progress_id = await _start_candidate(client, job_id, "Omar Hassan", "omar@example.com")
    completed_id = await _start_candidate(client, job_id, "Ahmed Ali", "ahmed@example.com")

    await client.post(
        f"/interviews/{in_progress_id}/answers", json={"answer": DETAILED_ANSWER}
    )
    for _ in question_ids:
        await client.post(
            f"/interviews/{completed_id}/answers", json={"answer": DETAILED_ANSWER}
        )

    body = (await client.get(f"/jobs/{job_id}/interviews")).json()
    by_id = {c["interview_id"]: c for c in body}

    assert by_id[not_started_id]["status"] == "in_progress"  # graph already asks Q1 on start
    assert by_id[in_progress_id]["status"] == "in_progress"
    assert by_id[completed_id]["status"] == "completed"


async def test_recruiter_can_directly_access_a_completed_candidates_report(client):
    job_id, question_ids = await _create_job_with_plan(client)
    interview_id = await _start_candidate(client, job_id, "Ahmed Ali", "ahmed@example.com")
    for _ in question_ids:
        resp = await client.post(
            f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER}
        )
    assert resp.json()["finished"] is True

    # The candidate table already carries the score/recommendation...
    listing = (await client.get(f"/jobs/{job_id}/interviews")).json()
    summary = next(c for c in listing if c["interview_id"] == interview_id)
    assert summary["overall_score"] == pytest.approx(0.8)
    assert summary["recommendation"] == "hire"

    # ...and the full report is directly reachable by interview id, matching that summary.
    report = (await client.get(f"/interviews/{interview_id}/report")).json()
    assert report["overall_score"] == summary["overall_score"]
    assert report["recommendation"] == summary["recommendation"]


async def test_not_started_and_in_progress_sessions_have_no_score_or_recommendation(client):
    job_id, _ = await _create_job_with_plan(client)
    interview_id = await _start_candidate(client, job_id, "Lina Saleh", "lina@example.com")

    body = (await client.get(f"/jobs/{job_id}/interviews")).json()
    summary = next(c for c in body if c["interview_id"] == interview_id)
    assert summary["overall_score"] is None
    assert summary["recommendation"] is None


async def test_job_with_no_candidates_yet_returns_an_empty_list(client):
    job_id, _ = await _create_job_with_plan(client)
    resp = await client.get(f"/jobs/{job_id}/interviews")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_candidate_facing_endpoints_never_expose_recruiter_only_fields(client):
    """The candidate's own interview endpoints must never carry score, recommendation, or any
    other recruiter-only evaluation field - see the recruiter/candidate API-boundary review.
    """
    job_id, question_ids = await _create_job_with_plan(client)
    interview_id = await _start_candidate(client, job_id, "Ahmed Ali", "ahmed@example.com")

    forbidden_keys = {
        "score",
        "recommendation",
        "strengths",
        "weaknesses",
        "evidence",
        "overall_score",
        "last_evaluation",
        "decision",
    }

    start_body = (await client.get(f"/interviews/{interview_id}")).json()
    assert forbidden_keys.isdisjoint(start_body.keys())

    answer_body = (
        await client.post(
            f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER}
        )
    ).json()
    assert forbidden_keys.isdisjoint(answer_body.keys())

    # History entries (past Q&A shown to the candidate) must also stay evaluation-free.
    for turn in answer_body["history"]:
        assert forbidden_keys.isdisjoint(turn.keys())
