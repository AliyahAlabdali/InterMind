import asyncio

import pytest

from app.agents.interview_graph import build_interview_graph
from app.core.exceptions import (
    InterviewAlreadyCompleted,
    InterviewNotFound,
    InterviewStateUnavailable,
)
from app.domain.interview import InterviewStatus
from app.domain.interview_plan import (
    InterviewPlan,
    InterviewQuestion,
    QuestionCategory,
)
from app.domain.occupation import OccupationMatch
from app.llm.fake_client import FakeLLMClient
from app.repositories.in_memory import (
    InMemoryInterviewPlanRepository,
    InMemoryInterviewSessionRepository,
)
from app.repositories.ports import InterviewSession
from app.services.answer_evaluation import AnswerEvaluationService
from app.services.interview_session import (
    InterviewLockRegistry,
    InterviewSessionService,
    _to_interview_state,
)

DETAILED_ANSWER = (
    "I led a project where I diagnosed a race condition in a queue consumer, wrote a "
    "regression test to reproduce it, fixed the underlying lock ordering, and verified it "
    "in staging before shipping."
)
SHORT_ANSWER = "I did that once."


def _occupation_match() -> OccupationMatch:
    return OccupationMatch(onet_soc_code="15-1252.00", title="Software Developers", score=1.0)


def _make_plan(job_id: str = "job-1") -> InterviewPlan:
    return InterviewPlan(
        job_id=job_id,
        occupation_match=_occupation_match(),
        questions=[
            InterviewQuestion(
                id="q1", category=QuestionCategory.COMPETENCY, text="Q1?", target="A", grounding="g"
            ),
            InterviewQuestion(
                id="q2", category=QuestionCategory.COMPETENCY, text="Q2?", target="B", grounding="g"
            ),
            InterviewQuestion(
                id="q3", category=QuestionCategory.COMPETENCY, text="Q3?", target="C", grounding="g"
            ),
        ],
    )


def _make_service() -> InterviewSessionService:
    graph = build_interview_graph(AnswerEvaluationService(llm=FakeLLMClient()))
    return InterviewSessionService(
        graph=graph,
        plan_repo=InMemoryInterviewPlanRepository(),
        session_repo=InMemoryInterviewSessionRepository(),
        locks=InterviewLockRegistry(),
    )


# --- _to_interview_state validation -----------------------------------------------------


def test_to_interview_state_rejects_empty_checkpoint():
    with pytest.raises(InterviewStateUnavailable, match="no checkpointed state"):
        _to_interview_state("interview-1", {})


def test_to_interview_state_rejects_missing_required_field():
    with pytest.raises(InterviewStateUnavailable, match="missing required field"):
        _to_interview_state("interview-1", {"job_id": "job-1", "status": "in_progress"})


def test_to_interview_state_rejects_invalid_status_value():
    with pytest.raises(InterviewStateUnavailable, match="invalid status value"):
        _to_interview_state(
            "interview-1",
            {"job_id": "job-1", "status": "not-a-real-status", "asked_question_ids": []},
        )


def test_to_interview_state_rejects_invalid_job_id():
    with pytest.raises(InterviewStateUnavailable, match="invalid job_id"):
        _to_interview_state(
            "interview-1",
            {"job_id": "", "status": "in_progress", "asked_question_ids": []},
        )


def test_to_interview_state_accepts_well_formed_checkpoint():
    state = _to_interview_state(
        "interview-1",
        {
            "job_id": "job-1",
            "status": "in_progress",
            "asked_question_ids": ["q1"],
            "current_question_id": "q1",
            "current_question_text": "Q1?",
            "history": [],
        },
    )
    assert state.job_id == "job-1"
    assert state.status == InterviewStatus.IN_PROGRESS
    assert state.turn_index == 1


# --- service-level checkpoint/repository consistency ------------------------------------


async def test_get_state_on_orphaned_session_raises_state_unavailable():
    """A session recorded in the repo with no matching graph checkpoint (repo/graph desync)
    must surface as a controlled error, not a raw KeyError."""
    service = _make_service()
    orphan = await service.session_repo.add(InterviewSession(job_id="job-1", id="orphan-thread"))
    with pytest.raises(InterviewStateUnavailable):
        await service.get_state(orphan.id)


async def test_submit_answer_on_orphaned_session_raises_state_unavailable():
    service = _make_service()
    orphan = await service.session_repo.add(InterviewSession(job_id="job-1", id="orphan-thread-2"))
    with pytest.raises(InterviewStateUnavailable):
        await service.submit_answer(orphan.id, DETAILED_ANSWER)


async def test_get_state_unknown_interview_raises_not_found():
    service = _make_service()
    with pytest.raises(InterviewNotFound):
        await service.get_state("does-not-exist")


# --- duplicate / concurrent submissions --------------------------------------------------


async def test_duplicate_sequential_submission_advances_each_time():
    service = _make_service()
    await service.plan_repo.add(_make_plan())
    interview_id, state = await service.start("job-1")
    assert state.current_question_id == "q1"

    first = await service.submit_answer(interview_id, DETAILED_ANSWER)
    assert first.current_question_id == "q2"

    # Submitting again (e.g. a client retry) is treated as the answer to the now-current
    # question - it must not crash or corrupt state.
    second = await service.submit_answer(interview_id, DETAILED_ANSWER)
    assert second.current_question_id == "q3"
    assert second.asked_question_ids == ["q1", "q2", "q3"]


async def test_concurrent_submissions_serialize_without_corruption():
    service = _make_service()
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    results = await asyncio.gather(
        service.submit_answer(interview_id, DETAILED_ANSWER),
        service.submit_answer(interview_id, DETAILED_ANSWER),
    )

    final = await service.get_state(interview_id)
    assert final.asked_question_ids == ["q1", "q2", "q3"]
    assert len(set(final.asked_question_ids)) == 3
    assert {r.current_question_id for r in results} <= {"q2", "q3", None}


async def test_submit_after_completion_raises_already_completed():
    service = _make_service()
    plan = InterviewPlan(
        job_id="job-1",
        occupation_match=_occupation_match(),
        questions=[
            InterviewQuestion(
                id="q1", category=QuestionCategory.COMPETENCY, text="Q1?", target="A", grounding="g"
            )
        ],
    )
    await service.plan_repo.add(plan)
    interview_id, _ = await service.start("job-1")

    completed = await service.submit_answer(interview_id, DETAILED_ANSWER)
    assert completed.status == InterviewStatus.COMPLETED

    with pytest.raises(InterviewAlreadyCompleted):
        await service.submit_answer(interview_id, DETAILED_ANSWER)


# --- multi-turn follow-up flow -----------------------------------------------------------


async def test_multi_turn_follow_up_then_advance_across_questions():
    service = _make_service()
    await service.plan_repo.add(_make_plan())
    interview_id, state = await service.start("job-1")
    assert state.current_question_id == "q1"

    follow_up = await service.submit_answer(interview_id, SHORT_ANSWER)
    assert follow_up.current_question_id == "q1"  # still on q1, follow-up asked
    assert follow_up.history[-1]["evaluation"]["decision"] == "follow_up"

    advanced = await service.submit_answer(interview_id, DETAILED_ANSWER)
    assert advanced.current_question_id == "q2"
    assert advanced.history[-1]["evaluation"]["decision"] == "advance"

    follow_up_2 = await service.submit_answer(interview_id, SHORT_ANSWER)
    assert follow_up_2.current_question_id == "q2"

    advanced_2 = await service.submit_answer(interview_id, DETAILED_ANSWER)
    assert advanced_2.current_question_id == "q3"

    finished = await service.submit_answer(interview_id, DETAILED_ANSWER)
    assert finished.status == InterviewStatus.COMPLETED
