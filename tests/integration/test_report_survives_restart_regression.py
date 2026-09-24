"""A stored report must stay readable after the graph checkpoint is gone.

The interview *record* and the generated *report* are durable (PostgreSQL rows), but LangGraph
checkpoints to an in-memory saver, so a backend restart leaves interview rows whose live graph
state no longer exists. ``GET /interviews/{id}/report`` used to consult that state first, purely
to gate on "has this interview completed", and raised ``InterviewStateUnavailable`` (500) before
it ever looked in the report repository. The effect was that a completed, persisted report became
unreachable after a restart, and the candidate table listed the same interview as *not started*
with no score.

A stored report is itself durable proof that the interview completed - one is only ever written
after that gate - so it is now consulted first. These tests simulate the restart by clearing the
graph's checkpointer while leaving every repository intact, which is exactly the state a restart
produces when ``DATABASE_URL`` is set.

Note on scope: the repositories under test here are the in-memory ones the whole suite runs on.
They stand in for the persistent ones; the SQL implementations are not exercised by this suite
(see the README's testing note). What is being pinned is the *route's* ordering, which is where
the defect was, and that is storage-agnostic.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_onet_kb
from app.domain.interview import InterviewStatus
from app.knowledge.onet_kb import OnetKnowledgeBase
from tests.conftest import FIXTURES, recruiter_credentials

FIXTURE_KB_PATH = FIXTURES / "onet_kb_fixture.jsonl"
JD = "Backend Software Engineer\nPython and Git experience required. Critical thinking a must."

#: Enough answers to drive the fixture plan's three targets to completion.
ANSWERS = [
    "I built a Python payments service and versioned every schema migration in Git.",
    "I review pull requests daily and rebase feature branches before merging them.",
    "I weigh trade-offs in writing before committing to a design, then measure the result.",
    "I profile before optimising, and I keep the slow path measurable in production.",
    "I document the decision and what would make us revisit it.",
]


@pytest.fixture(autouse=True)
def _use_fixture_kb(app):
    app.dependency_overrides[get_onet_kb] = lambda: OnetKnowledgeBase(path=FIXTURE_KB_PATH)


def _forget_graph_state(app) -> None:
    """Simulate a backend restart: drop every LangGraph checkpoint, keep every repository.

    The graph is built once per process and cached on ``app.state`` (see
    ``app.api.deps.get_interview_graph``); replacing its checkpointer's storage is the same
    situation a fresh process starts in, without tearing down the repositories that a real
    deployment keeps in PostgreSQL.
    """
    graph = app.state.interview_graph
    checkpointer = graph.checkpointer
    for attribute in ("storage", "writes", "blobs"):
        container = getattr(checkpointer, attribute, None)
        if container is not None:
            container.clear()


async def _completed_interview(client) -> tuple[str, str]:
    """Run an interview to completion. Returns ``(job_id, interview_id)``."""
    job_id = (await client.post("/jobs", json={"job_description": JD})).json()["id"]
    assert (await client.post(f"/jobs/{job_id}/interview-plan")).status_code == 201

    started = (await client.post("/interviews", json={"job_id": job_id})).json()
    interview_id, token = started["interview_id"], started["candidate_access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    state = started
    for answer in ANSWERS:
        if state.get("status") == InterviewStatus.COMPLETED.value:
            break
        response = await client.post(
            f"/interviews/{interview_id}/answers", json={"answer": answer}, headers=headers
        )
        assert response.status_code == 200, response.text
        state = response.json()

    assert state["status"] == InterviewStatus.COMPLETED.value, "interview did not complete"
    return job_id, interview_id


@pytest.fixture
async def recruiter(app):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    signup = await client.post(
        "/auth/recruiter/signup", json=recruiter_credentials("restart@intermind.test")
    )
    assert signup.status_code == 201, signup.text
    yield client
    await client.aclose()


async def test_a_stored_report_is_still_readable_after_the_checkpoint_is_gone(app, recruiter):
    """The defect: this returned 500 once the in-memory checkpoint was cleared."""
    _, interview_id = await _completed_interview(recruiter)

    before = await recruiter.get(f"/interviews/{interview_id}/report")
    assert before.status_code == 200, before.text

    _forget_graph_state(app)

    after = await recruiter.get(f"/interviews/{interview_id}/report")

    assert after.status_code == 200, after.text
    assert after.json()["interview_id"] == interview_id
    assert after.json() == before.json(), "the report changed across the simulated restart"


async def test_the_candidate_table_still_shows_a_completed_interview_after_a_restart(
    app, recruiter
):
    """The same root cause, seen by the recruiter: a finished interview was listed as
    `not_started` with no score, because the listing also asked the graph first."""
    job_id, interview_id = await _completed_interview(recruiter)
    assert (await recruiter.get(f"/interviews/{interview_id}/report")).status_code == 200

    _forget_graph_state(app)

    listing = await recruiter.get(f"/jobs/{job_id}/interviews")

    assert listing.status_code == 200
    row = next(r for r in listing.json() if r["interview_id"] == interview_id)
    assert row["status"] == InterviewStatus.COMPLETED.value
    assert row["overall_score"] is not None
    assert row["recommendation"] is not None


async def test_an_interview_with_no_report_and_no_state_is_not_claimed_to_be_complete(
    app, recruiter
):
    """The fallback must not over-claim: without a stored report there is nothing durable
    saying the interview finished, so it still lists as not started rather than complete."""
    job_id = (await recruiter.post("/jobs", json={"job_description": JD})).json()["id"]
    await recruiter.post(f"/jobs/{job_id}/interview-plan")
    started = (await recruiter.post("/interviews", json={"job_id": job_id})).json()

    _forget_graph_state(app)

    listing = await recruiter.get(f"/jobs/{job_id}/interviews")

    row = next(
        r for r in listing.json() if r["interview_id"] == started["interview_id"]
    )
    assert row["status"] == InterviewStatus.NOT_STARTED.value
    assert row["overall_score"] is None


async def test_an_unfinished_interview_still_reports_409_rather_than_a_report(app, recruiter):
    """The completion gate is unchanged for the normal path: no stored report means the graph
    is still the authority, and an in-progress interview has no report to serve."""
    job_id = (await recruiter.post("/jobs", json={"job_description": JD})).json()["id"]
    await recruiter.post(f"/jobs/{job_id}/interview-plan")
    started = (await recruiter.post("/interviews", json={"job_id": job_id})).json()

    response = await recruiter.get(f"/interviews/{started['interview_id']}/report")

    assert response.status_code == 409


async def test_another_recruiter_still_cannot_read_a_restored_report(app, recruiter):
    """Serving the stored report earlier must not move it in front of the ownership check."""
    _, interview_id = await _completed_interview(recruiter)
    assert (await recruiter.get(f"/interviews/{interview_id}/report")).status_code == 200
    _forget_graph_state(app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        await other.post(
            "/auth/recruiter/signup", json=recruiter_credentials("other@intermind.test")
        )
        response = await other.get(f"/interviews/{interview_id}/report")

    assert response.status_code == 404
