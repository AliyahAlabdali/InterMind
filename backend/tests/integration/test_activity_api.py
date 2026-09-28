"""Integration tests for the recruiter activity feed (`GET /activity`).

The feed exists so the recruiter workspace can show what the adaptive interview actually did
without the frontend inventing events. These tests therefore assert the events are *derived
from real transitions* - an interview that was really started, evidence that was really
recorded, a follow-up the graph really decided on - and that the endpoint sits behind the same
recruiter boundary as the rest of the recruiter-only surface.
"""

from __future__ import annotations

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


async def _create_job_with_plan(client) -> tuple[str, list[str]]:
    jd = "Backend Software Engineer\nPython and Git experience required. Critical thinking a must."
    job_resp = await client.post("/jobs", json={"job_description": jd})
    job_id = job_resp.json()["id"]
    plan_resp = await client.post(f"/jobs/{job_id}/interview-plan")
    question_ids = [t["id"] for t in plan_resp.json()["coverage_targets"]]
    return job_id, question_ids


async def _start_candidate(client, job_id: str, name: str = "Ahmed Ali") -> str:
    resp = await client.post(
        "/interviews", json={"job_id": job_id, "candidate_name": name, "candidate_email": ""}
    )
    assert resp.status_code == 201
    return resp.json()["interview_id"]


async def test_activity_is_empty_before_anything_happens(client):
    resp = await client.get("/activity")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_starting_an_interview_records_a_real_event(client):
    job_id, _ = await _create_job_with_plan(client)
    interview_id = await _start_candidate(client, job_id, name="Sara Mohammed")

    events = (await client.get("/activity")).json()
    assert len(events) == 1
    event = events[0]
    assert event["type"] == "interview_started"
    assert event["interview_id"] == interview_id
    assert event["job_id"] == job_id
    assert event["candidate_name"] == "Sara Mohammed"
    assert event["target"] is None


async def test_answering_records_evidence_and_completion_events(client):
    job_id, question_ids = await _create_job_with_plan(client)
    interview_id = await _start_candidate(client, job_id)

    for _ in question_ids:
        await client.post(f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER})

    events = (await client.get("/activity", params={"limit": 100})).json()
    types = [e["type"] for e in events]

    # Newest first: the completion is the most recent thing that happened.
    assert types[0] == "interview_completed"
    assert "evidence_detected" in types
    # Every evidence event names the target it was recorded against, never a guess.
    evidence_events = [e for e in events if e["type"] == "evidence_detected"]
    assert evidence_events
    assert all(e["interview_id"] == interview_id for e in evidence_events)
    assert all(e["target"] for e in evidence_events)


async def test_a_follow_up_decision_is_recorded_as_its_own_event(client):
    job_id, _ = await _create_job_with_plan(client)
    interview_id = await _start_candidate(client, job_id)

    # A thin answer is what makes the graph decide to go deeper - see the evaluator's
    # follow-up resolution. The event must reflect that real decision, not be synthesised.
    await client.post(f"/interviews/{interview_id}/answers", json={"answer": SHORT_ANSWER})

    events = (await client.get("/activity", params={"limit": 100})).json()
    follow_ups = [e for e in events if e["type"] == "follow_up_generated"]
    recorded_types = [e["type"] for e in events]
    assert follow_ups, f"expected a follow_up_generated event, got types={recorded_types}"
    assert follow_ups[0]["interview_id"] == interview_id


async def test_events_are_newest_first_and_respect_limit(client):
    job_id, _ = await _create_job_with_plan(client)
    await _start_candidate(client, job_id, name="First Candidate")
    await _start_candidate(client, job_id, name="Second Candidate")
    await _start_candidate(client, job_id, name="Third Candidate")

    all_events = (await client.get("/activity")).json()
    assert [e["candidate_name"] for e in all_events[:3]] == [
        "Third Candidate",
        "Second Candidate",
        "First Candidate",
    ]

    limited = (await client.get("/activity", params={"limit": 2})).json()
    assert len(limited) == 2
    assert limited[0]["candidate_name"] == "Third Candidate"


async def test_activity_feed_is_recruiter_only(app):
    """Same boundary as the candidate listing - the feed names candidates and their assessed
    targets, so a candidate credential must not reach it."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as recruiter:
        # Registers for real: recruiters are persistent accounts now.
        assert (
            await recruiter.post("/auth/recruiter/signup", json=recruiter_credentials())
        ).status_code == 201
        job_id, _ = await _create_job_with_plan(recruiter)
        start = await recruiter.post(
            "/interviews", json={"job_id": job_id, "candidate_name": "Ahmed Ali"}
        )
        candidate_token = start.json()["candidate_access_token"]

    async with AsyncClient(transport=transport, base_url="http://test") as anonymous:
        assert (await anonymous.get("/activity")).status_code == 401

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {candidate_token}"},
    ) as candidate:
        assert (await candidate.get("/activity")).status_code == 401
