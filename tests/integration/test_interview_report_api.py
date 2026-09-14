import pytest

from app.api.deps import get_onet_kb
from app.knowledge.onet_kb import OnetKnowledgeBase
from app.repositories.ports import InterviewSession
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


async def _create_job_with_plan(client) -> tuple[str, list[dict]]:
    jd = "Backend Software Engineer\nPython and Git experience required. Critical thinking a must."
    job_resp = await client.post("/jobs", json={"job_description": jd})
    job_id = job_resp.json()["id"]

    plan_resp = await client.post(f"/jobs/{job_id}/interview-plan")
    return job_id, plan_resp.json()["questions"]


async def _complete_interview(client, job_id: str, questions: list[dict]) -> str:
    start = await client.post("/interviews", json={"job_id": job_id})
    interview_id = start.json()["interview_id"]
    for _ in questions:
        resp = await client.post(
            f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER}
        )
    assert resp.json()["finished"] is True
    return interview_id


async def test_report_for_completed_interview_covers_every_question(client):
    job_id, questions = await _create_job_with_plan(client)
    interview_id = await _complete_interview(client, job_id, questions)

    resp = await client.get(f"/interviews/{interview_id}/report")
    assert resp.status_code == 200
    report = resp.json()

    assert report["interview_id"] == interview_id
    assert report["job_id"] == job_id
    assert {qe["question_id"] for qe in report["question_evaluations"]} == {
        q["id"] for q in questions
    }
    for qe in report["question_evaluations"]:
        assert qe["score"] is not None
        assert qe["decision"] == "advance"
        assert qe["evidence"]  # evidence preserved, non-empty

    assert {c["name"] for c in report["competencies"]} == {q["target"] for q in questions}
    assert report["summary"]
    assert report["recommendation"] in {"strong_hire", "hire", "consider", "no_hire"}


async def test_report_overall_score_and_recommendation_are_deterministic(client):
    job_id, questions = await _create_job_with_plan(client)
    interview_id = await _complete_interview(client, job_id, questions)

    resp = await client.get(f"/interviews/{interview_id}/report")
    report = resp.json()

    # FakeLLMClient always scores a detailed answer at 0.8/advance, so every category average
    # is 0.8 and the weighted overall score is exactly 0.8 regardless of category mix.
    assert report["overall_score"] == pytest.approx(0.8)
    assert report["recommendation"] == "hire"


async def test_repeated_report_requests_are_idempotent(client):
    job_id, questions = await _create_job_with_plan(client)
    interview_id = await _complete_interview(client, job_id, questions)

    first = await client.get(f"/interviews/{interview_id}/report")
    second = await client.get(f"/interviews/{interview_id}/report")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


async def test_report_before_completion_returns_409(client):
    job_id, questions = await _create_job_with_plan(client)
    start = await client.post("/interviews", json={"job_id": job_id})
    interview_id = start.json()["interview_id"]

    resp = await client.get(f"/interviews/{interview_id}/report")
    assert resp.status_code == 409


async def test_report_for_unknown_interview_returns_404(client):
    resp = await client.get("/interviews/does-not-exist/report")
    assert resp.status_code == 404


async def test_report_with_missing_checkpoint_returns_sanitized_500(app, client):
    session_repo = app.state.interview_session_repository
    orphan = await session_repo.add(InterviewSession(job_id="does-not-matter", id="orphan-report"))

    resp = await client.get(f"/interviews/{orphan.id}/report")
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Interview state is currently unavailable."}


async def test_report_reflects_a_weak_final_answer_without_inventing_success(client):
    job_id, questions = await _create_job_with_plan(client)
    start = await client.post("/interviews", json={"job_id": job_id})
    interview_id = start.json()["interview_id"]

    short_answer = "I did that once."
    # Two short answers in a row: first triggers a follow-up, second is still weak but the
    # one-follow-up cap forces the graph to advance anyway (see interview_graph.py).
    await client.post(f"/interviews/{interview_id}/answers", json={"answer": short_answer})
    await client.post(f"/interviews/{interview_id}/answers", json={"answer": short_answer})
    resp = None
    for _ in range(len(questions) - 1):
        resp = await client.post(
            f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER}
        )
    assert resp.json()["finished"] is True

    report = (await client.get(f"/interviews/{interview_id}/report")).json()
    first_question_eval = next(
        qe for qe in report["question_evaluations"] if qe["question_id"] == questions[0]["id"]
    )
    # The report must honestly reflect the weak final answer (follow_up/0.3), not claim the
    # candidate advanced cleanly just because the interview moved on.
    assert first_question_eval["decision"] == "follow_up"
    assert first_question_eval["score"] == pytest.approx(0.3)
