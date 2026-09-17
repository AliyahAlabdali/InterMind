import asyncio

import pytest

from app.api.deps import get_llm_client, get_onet_kb
from app.core.exceptions import LLMError
from app.domain.interview_plan import GeneratedQuestion, GeneratedQuestionSet
from app.knowledge.onet_kb import OnetKnowledgeBase
from app.llm.fake_client import FakeLLMClient
from app.repositories.ports import InterviewSession
from tests.conftest import FIXTURES

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
    # Coverage-target ids are computed the same deterministic way the interview graph computes
    # them at runtime (see app.services.target_identity) - so, for this JD's targets (all
    # required, no O*NET-context-driven reordering possible since none is O*NET-sourced), the
    # order the adaptive interview actually asks them in matches this list exactly.
    question_ids = [t["id"] for t in plan_resp.json()["coverage_targets"]]
    return job_id, question_ids


async def test_start_interview_returns_first_question(client):
    job_id, question_ids = await _create_job_with_plan(client)

    resp = await client.post("/interviews", json={"job_id": job_id})
    assert resp.status_code == 201
    body = resp.json()
    assert body["job_id"] == job_id
    assert body["status"] == "in_progress"
    assert body["finished"] is False
    assert body["current_question_id"] == question_ids[0]
    assert body["current_question_text"]
    assert body["asked_question_ids"] == [question_ids[0]]
    assert body["current_question_is_follow_up"] is False
    # Candidate-facing response must never carry recruiter-only evaluation fields.
    assert "last_evaluation" not in body
    assert "score" not in body
    assert "recommendation" not in body


async def test_start_interview_without_plan_returns_404(client):
    resp = await client.post("/interviews", json={"job_id": "does-not-exist"})
    assert resp.status_code == 404


async def test_short_answer_triggers_one_follow_up_then_advances(client):
    job_id, question_ids = await _create_job_with_plan(client)
    start = await client.post("/interviews", json={"job_id": job_id})
    interview_id = start.json()["interview_id"]

    follow_up = await client.post(
        f"/interviews/{interview_id}/answers", json={"answer": SHORT_ANSWER}
    )
    assert follow_up.status_code == 200
    follow_up_body = follow_up.json()
    assert follow_up_body["current_question_id"] == question_ids[0]
    assert follow_up_body["current_question_is_follow_up"] is True

    advanced = await client.post(
        f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER}
    )
    assert advanced.status_code == 200
    advanced_body = advanced.json()
    assert advanced_body["current_question_is_follow_up"] is False
    assert advanced_body["current_question_id"] == question_ids[1]


async def test_regression_5_api_response_history_contains_both_turns_correctly(client):
    """Regression test 5: the candidate-facing `GET /interviews/{id}` response's `history`
    must show the follow-up as its own turn - its own id, its own (follow-up) question text,
    and the follow-up's own answer - never the original question's id/text repeated back."""
    job_id, question_ids = await _create_job_with_plan(client)
    start = await client.post("/interviews", json={"job_id": job_id})
    interview_id = start.json()["interview_id"]

    await client.post(f"/interviews/{interview_id}/answers", json={"answer": SHORT_ANSWER})
    advanced = await client.post(
        f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER}
    )
    body = advanced.json()

    status = await client.get(f"/interviews/{interview_id}")
    assert status.json() == body  # GET reflects the same state, not just the POST response

    history = body["history"]
    assert len(history) == 2
    original_turn, follow_up_turn = history
    assert original_turn["question_id"] == question_ids[0]
    assert original_turn["answer"] == SHORT_ANSWER

    assert follow_up_turn["question_id"] != question_ids[0]
    assert follow_up_turn["question_id"] not in question_ids  # not a planned question's id
    assert follow_up_turn["question"] != original_turn["question"]
    assert follow_up_turn["answer"] == DETAILED_ANSWER


async def test_detailed_answers_complete_the_interview(client):
    job_id, question_ids = await _create_job_with_plan(client)
    start = await client.post("/interviews", json={"job_id": job_id})
    interview_id = start.json()["interview_id"]

    body = start.json()
    for _ in question_ids:
        resp = await client.post(
            f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER}
        )
        assert resp.status_code == 200
        body = resp.json()

    assert body["finished"] is True
    assert body["status"] == "completed"
    assert body["current_question_id"] is None
    assert set(body["asked_question_ids"]) == set(question_ids)

    status_resp = await client.get(f"/interviews/{interview_id}")
    assert status_resp.status_code == 200
    assert status_resp.json() == body


async def test_two_short_answers_advance_after_one_follow_up(client):
    job_id, question_ids = await _create_job_with_plan(client)
    start = await client.post("/interviews", json={"job_id": job_id})
    interview_id = start.json()["interview_id"]

    first = await client.post(
        f"/interviews/{interview_id}/answers", json={"answer": SHORT_ANSWER}
    )
    assert first.json()["current_question_id"] == question_ids[0]

    second = await client.post(
        f"/interviews/{interview_id}/answers", json={"answer": SHORT_ANSWER}
    )
    second_body = second.json()
    # Only one follow-up is allowed per question; a second weak answer still advances - to a
    # genuinely new question, which must not be misreported as a follow-up of the old one.
    assert second_body["current_question_id"] == question_ids[1]
    assert second_body["current_question_is_follow_up"] is False


async def test_get_unknown_interview_returns_404(client):
    resp = await client.get("/interviews/does-not-exist")
    assert resp.status_code == 404


async def test_submit_answer_to_unknown_interview_returns_404(client):
    resp = await client.post("/interviews/does-not-exist/answers", json={"answer": "hi"})
    assert resp.status_code == 404


async def test_submit_answer_after_completion_returns_409(client):
    job_id, question_ids = await _create_job_with_plan(client)
    start = await client.post("/interviews", json={"job_id": job_id})
    interview_id = start.json()["interview_id"]

    for _ in question_ids:
        resp = await client.post(
            f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER}
        )
    assert resp.json()["finished"] is True

    again = await client.post(
        f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER}
    )
    assert again.status_code == 409


@pytest.mark.parametrize("blank", ["   ", "\n\t", ""])
async def test_whitespace_only_answer_rejected_with_422(client, blank):
    job_id, _ = await _create_job_with_plan(client)
    start = await client.post("/interviews", json={"job_id": job_id})
    interview_id = start.json()["interview_id"]

    resp = await client.post(f"/interviews/{interview_id}/answers", json={"answer": blank})
    assert resp.status_code == 422


async def test_duplicate_sequential_submission_does_not_crash(client):
    job_id, question_ids = await _create_job_with_plan(client)
    start = await client.post("/interviews", json={"job_id": job_id})
    interview_id = start.json()["interview_id"]

    first = await client.post(
        f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER}
    )
    assert first.status_code == 200
    assert first.json()["current_question_id"] == question_ids[1]

    # A duplicate/retried submission is simply treated as the answer to the now-current
    # question - it must not crash or corrupt state.
    second = await client.post(
        f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER}
    )
    assert second.status_code == 200
    assert second.json()["current_question_id"] == question_ids[2]
    assert second.json()["asked_question_ids"] == question_ids[:3]


async def test_concurrent_submissions_over_http_do_not_corrupt_state(client):
    job_id, question_ids = await _create_job_with_plan(client)
    start = await client.post("/interviews", json={"job_id": job_id})
    interview_id = start.json()["interview_id"]

    responses = await asyncio.gather(
        client.post(f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER}),
        client.post(f"/interviews/{interview_id}/answers", json={"answer": DETAILED_ANSWER}),
    )
    assert all(r.status_code == 200 for r in responses)

    final = await client.get(f"/interviews/{interview_id}")
    asked = final.json()["asked_question_ids"]
    assert asked == question_ids[:3]
    assert len(set(asked)) == len(asked)


async def test_orphaned_interview_session_returns_sanitized_500(app, client):
    """Repository/graph-checkpointer desync (session recorded, no matching checkpoint) must
    surface as a stable, generic 500 - not a raw KeyError/stack trace."""
    session_repo = app.state.interview_session_repository
    orphan = await session_repo.add(InterviewSession(job_id="does-not-matter", id="orphan-id"))

    resp = await client.get(f"/interviews/{orphan.id}")
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Interview state is currently unavailable."}


class _FailingLLMClient:
    async def generate_structured(self, *, prompt, input_text, schema):
        raise LLMError("upstream provider said: api_key=sk-super-secret-do-not-leak")


async def test_llm_failure_returns_sanitized_generic_error(app, client):
    app.dependency_overrides[get_llm_client] = lambda: _FailingLLMClient()

    resp = await client.post("/jobs", json={"job_description": "Software Engineer\nPython."})

    assert resp.status_code == 502
    body = resp.json()
    assert body == {"detail": "The language model provider failed to process the request."}
    assert "sk-super-secret" not in resp.text


class _WrongTargetQuestionClient:
    """Delegates JD-analysis/answer-evaluation calls to a real FakeLLMClient, but always
    returns a question for an unrequested target - reproducing the exact reported production
    incident (a real OpenAI call generating a question for `competency: collaboration` /
    `task: develop restful apis` instead of the actually-selected runtime target) without a
    live OpenAI call. Used to prove the end-to-end, over-HTTP behaviour once BOTH the first
    attempt and the bounded retry fail (see app.services.question_generation): a sanitized
    502, never a 500, and never the raw "unrequested target(s)" message."""

    def __init__(self):
        self._fake = FakeLLMClient()

    async def generate_structured(self, *, prompt, input_text, schema):
        if schema is GeneratedQuestionSet:
            return GeneratedQuestionSet(
                questions=[
                    GeneratedQuestion(
                        category="task", target="Some other target", text="Unrelated question?"
                    )
                ]
            )
        return await self._fake.generate_structured(
            prompt=prompt, input_text=input_text, schema=schema
        )


async def test_runtime_question_generation_failure_after_retry_returns_sanitized_502(app, client):
    job_id, _ = await _create_job_with_plan(client)
    app.dependency_overrides[get_llm_client] = lambda: _WrongTargetQuestionClient()

    resp = await client.post("/interviews", json={"job_id": job_id})

    assert resp.status_code == 502
    assert resp.json() == {"detail": "The language model provider failed to process the request."}
    assert "unrequested target" not in resp.text.lower()
    assert "collaboration" not in resp.text.lower()
