import asyncio

import pytest

from app.agents.interview_graph import build_interview_graph
from app.core.exceptions import (
    InterviewAlreadyCompleted,
    InterviewNotFound,
    InterviewStateUnavailable,
)
from app.domain.evaluation import AnswerEvaluation, AnswerEvidenceType, EvaluationDecision
from app.domain.interview import InterviewStatus
from app.domain.interview_plan import (
    CoverageTarget,
    EvidenceSource,
    GeneratedQuestion,
    GeneratedQuestionSet,
    InterviewPlan,
    QuestionCategory,
    RequirementLevel,
)
from app.domain.occupation import OccupationMatch
from app.llm.fake_client import FakeLLMClient
from app.repositories.in_memory import (
    InMemoryCandidateRepository,
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
from app.services.question_generation import QuestionGenerationService


# The old fixed-script plan pre-generated question text ("Q1?", "Q2?", "Q3?") once, upfront.
# Under the adaptive architecture, that text is generated at runtime, one target at a time, as
# the interview actually reaches it - see `app.agents.interview_graph.select_target`. This
# client reproduces the exact same "Q1?"/"Q2?"/"Q3?" sequence deterministically so the bulk of
# this file's existing assertions (about ids, history, follow-up behaviour - none of which care
# what the literal question text is, just that it's controllable and distinct per target) keep
# working unchanged; a few tests below assert on the runtime-generation mechanism itself.
class _ScriptedQuestionClient:
    def __init__(self, texts: list[str]):
        self._texts = iter(texts)
        self.calls: list[str] = []

    async def generate_structured(self, *, prompt, input_text, schema):
        assert schema is GeneratedQuestionSet, f"unexpected schema requested: {schema}"
        self.calls.append(input_text)
        category = target = None
        for line in input_text.splitlines():
            stripped = line.strip()
            for cat in ("COMPETENCY", "TECHNOLOGY", "TASK"):
                if stripped.upper().startswith(f"{cat}:"):
                    category = cat.lower()
                    target = stripped.partition(":")[2].strip()
        assert category is not None, f"no target line found in: {input_text!r}"
        return GeneratedQuestionSet(
            questions=[GeneratedQuestion(category=category, target=target, text=next(self._texts))]
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
        role_title="Software Developer",
        occupation_match=_occupation_match(),
        coverage_targets=[
            CoverageTarget(
                id="q1",
                category=QuestionCategory.COMPETENCY,
                target="A",
                requirement_level=RequirementLevel.REQUIRED,
                source=EvidenceSource.JOBSPEC,
                priority=0,
                grounding="g",
            ),
            CoverageTarget(
                id="q2",
                category=QuestionCategory.COMPETENCY,
                target="B",
                requirement_level=RequirementLevel.REQUIRED,
                source=EvidenceSource.JOBSPEC,
                priority=1,
                grounding="g",
            ),
            CoverageTarget(
                id="q3",
                category=QuestionCategory.COMPETENCY,
                target="C",
                requirement_level=RequirementLevel.REQUIRED,
                source=EvidenceSource.JOBSPEC,
                priority=2,
                grounding="g",
            ),
        ],
    )


def _make_service(llm=None, question_texts=("Q1?", "Q2?", "Q3?")) -> InterviewSessionService:
    graph = build_interview_graph(
        AnswerEvaluationService(llm=llm or FakeLLMClient()),
        QuestionGenerationService(llm=_ScriptedQuestionClient(list(question_texts))),
    )
    return InterviewSessionService(
        graph=graph,
        plan_repo=InMemoryInterviewPlanRepository(),
        session_repo=InMemoryInterviewSessionRepository(),
        candidate_repo=InMemoryCandidateRepository(),
        locks=InterviewLockRegistry(),
    )


class _ScriptedEvaluationClient:
    """Returns pre-built `AnswerEvaluation` objects in order, one per `evaluate()` call -
    lets a test script exactly the evaluation a real LLM produced in the reported bug (a
    strong-looking answer whose own `decision` says `advance` despite a recorded, specific
    evidence gap and a ready-made follow-up question), deterministically and offline.

    Also records the raw `input_text` sent for each call, so a test can assert on exactly what
    question text/category/target the evaluator was actually given for a given turn - this is
    the only way to observe the evaluator-context bug (FakeLLMClient's own scoring ignores the
    `QUESTION:` line entirely, so it can't surface this by itself).
    """

    def __init__(self, responses: list[AnswerEvaluation]):
        self._responses = iter(responses)
        self.calls: list[str] = []

    async def generate_structured(self, *, prompt, input_text, schema):
        assert schema is AnswerEvaluation, f"unexpected schema requested: {schema}"
        self.calls.append(input_text)
        return next(self._responses)


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
        role_title="Software Developer",
        occupation_match=_occupation_match(),
        coverage_targets=[
            CoverageTarget(
                id="q1",
                category=QuestionCategory.COMPETENCY,
                target="A",
                requirement_level=RequirementLevel.REQUIRED,
                source=EvidenceSource.JOBSPEC,
                priority=0,
                grounding="g",
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


async def test_one_answer_submission_advances_exactly_once():
    """A single detailed answer must move the interview forward by exactly one question.

    Regression test: previously the candidate had to submit twice per question in some
    circumstances - see the follow-up-text regression test below for the actual root cause.
    This covers the plain advance path stays a strict one-submission-per-question loop.
    """
    service = _make_service()
    await service.plan_repo.add(_make_plan())
    interview_id, state = await service.start("job-1")
    assert state.turn_index == 1
    assert state.asked_question_ids == ["q1"]

    after_one = await service.submit_answer(interview_id, DETAILED_ANSWER)
    assert after_one.current_question_id == "q2"
    assert after_one.asked_question_ids == ["q1", "q2"]  # exactly one new question asked
    assert after_one.turn_index == 2


async def test_follow_up_does_not_require_resubmitting_the_original_answer():
    """A follow-up must present *different* question text than the original question, and one
    submission in response to it must be enough to advance.

    Regression test for a real bug: `evaluate_answer` computed the follow-up phrasing but
    never wrote it into `current_question_text` before the graph's `follow_up_question` node
    interrupted, so the candidate was shown the *same* original question text again after
    their first answer. Functionally this meant the candidate's first answer was silently
    consumed as a (never-seen) follow-up prompt, and it took a second submission - answering
    what looked like an unchanged question - to actually move on. See `interview_graph.py`'s
    `evaluate_answer`/`follow_up_question` for the fix.
    """
    service = _make_service()
    await service.plan_repo.add(_make_plan())
    interview_id, initial_state = await service.start("job-1")
    original_question_text = initial_state.current_question_text
    assert original_question_text == "Q1?"

    follow_up = await service.submit_answer(interview_id, SHORT_ANSWER)
    assert follow_up.current_question_id == "q1"  # same underlying question slot
    # ... but the candidate must see a *different*, follow-up-specific prompt, not the
    # original question text repeated back at them.
    assert follow_up.current_question_text != original_question_text
    assert follow_up.current_question_text  # never blank

    # One submission in response to the (correctly-shown) follow-up must be enough to advance.
    advanced = await service.submit_answer(interview_id, DETAILED_ANSWER)
    assert advanced.current_question_id == "q2"


async def test_current_question_id_contract_during_a_follow_up():
    """Copilot review, SHOULD FIX 4: pins down the deliberate identity contract documented on
    `app.domain.interview.InterviewState` - reviewed and kept as-is rather than changed.

    Three distinct identities exist at any point in an interview, and the API only ever
    exposes two of them: the ROOT TARGET's id (`current_question_id` - stable across an entire
    follow-up), the ACTUAL CURRENT TURN's content (`current_question_text` - which *does*
    change once a follow-up is asked), and the FOLLOW-UP's own id (never exposed as
    `current_question_id` - only ever visible via `history`/`asked_question_ids`, each tagged
    with its `root_question_id`).
    """
    service = _make_service()
    await service.plan_repo.add(_make_plan())
    interview_id, initial_state = await service.start("job-1")
    root_id = initial_state.current_question_id
    assert root_id == "q1"
    original_text = initial_state.current_question_text

    # First submission: a weak answer to the ROOT question itself triggers a follow-up. This
    # turn's own question_id is still the root id - it hasn't been asked the follow-up yet.
    follow_up_state = await service.submit_answer(interview_id, SHORT_ANSWER)
    assert follow_up_state.history[-1]["question_id"] == root_id

    # Root target identity: unchanged by the follow-up.
    assert follow_up_state.current_question_id == root_id
    # Actual current turn content: changed to the follow-up's own phrasing.
    assert follow_up_state.current_question_text != original_text
    assert follow_up_state.current_question_text

    # Second submission: answering the follow-up itself. THIS turn's own identity is the
    # follow-up's - distinct from the root id, and never what current_question_id reports,
    # even though it was the answer that resolved this same root target.
    advanced_state = await service.submit_answer(interview_id, DETAILED_ANSWER)
    follow_up_turn = advanced_state.history[-1]
    follow_up_id = follow_up_turn["question_id"]
    assert follow_up_id != root_id
    assert follow_up_turn["root_question_id"] == root_id
    assert follow_up_id in advanced_state.asked_question_ids

    # current_question_id has already moved on to the NEXT target's root id - never to the
    # follow-up's own id, which simply stops being "current" anything once it resolves.
    assert advanced_state.current_question_id not in (root_id, follow_up_id)


async def test_viewing_previous_questions_does_not_corrupt_interview_state():
    """Candidate "previous question" navigation is read-only `GET` polling (`get_state`), never
    `submit_answer` - repeating it must never advance, regenerate, or otherwise mutate the
    interview, regardless of how many times or in what order it's called relative to real
    answer submissions.
    """
    service = _make_service()
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    # Simulate a candidate repeatedly navigating back to review question 1 before answering.
    for _ in range(5):
        state = await service.get_state(interview_id)
        assert state.current_question_id == "q1"
        assert state.asked_question_ids == ["q1"]
        assert state.history == []

    after_q1 = await service.submit_answer(interview_id, DETAILED_ANSWER)
    assert after_q1.current_question_id == "q2"
    assert after_q1.asked_question_ids == ["q1", "q2"]

    # More "back navigation" polling after answering q1 - still must not disturb progression.
    for _ in range(5):
        state = await service.get_state(interview_id)
        assert state.current_question_id == "q2"
        assert state.asked_question_ids == ["q1", "q2"]
        assert len(state.history) == 1
        assert state.history[0]["question_id"] == "q1"

    after_q2 = await service.submit_answer(interview_id, DETAILED_ANSWER)
    assert after_q2.current_question_id == "q3"
    assert after_q2.asked_question_ids == ["q1", "q2", "q3"]


# --- autonomous follow-up: the graph acts on the evaluator's evidence signal, not just its
# --- one-shot `decision` field (regression coverage for the reported real-OpenAI bug) --------


def _strong_evaluation() -> AnswerEvaluation:
    return AnswerEvaluation(
        score=0.9,
        evidence_type=AnswerEvidenceType.DEMONSTRATED,
        decision=EvaluationDecision.ADVANCE,
        follow_up_needed=False,
    )


def _gap_evaluation(follow_up_question: str | None) -> AnswerEvaluation:
    """A strong-looking answer whose own `decision` under-calls a follow-up it should have
    asked for - the exact shape of the reported real-OpenAI bug, stated generically (no
    specific target/domain baked in - see the requirement that this must generalize)."""
    return AnswerEvaluation(
        score=0.85,
        evidence_type=AnswerEvidenceType.DEMONSTRATED,
        decision=EvaluationDecision.ADVANCE,  # the model's own (miscalibrated) guess
        strengths=["Described a real, specific piece of work."],
        weaknesses=["A specific metric/number mentioned was never actually given."],
        evidence=["a close paraphrase of the answer"],
        follow_up_needed=False,  # deliberately inconsistent with follow_up_question, like a
        # real model's output can be - the system must not depend on this being consistent.
        follow_up_question=follow_up_question,
    )


async def test_meaningful_evidence_gap_triggers_a_follow_up_despite_a_raw_advance_decision():
    """Test B/D: even though the scripted evaluation's own `decision` is `advance`, a real,
    specific evidence gap (`weaknesses` + a concrete `follow_up_question`) must still produce
    a follow-up - reproducing the reported bug's exact shape end-to-end through the graph."""
    llm = _ScriptedEvaluationClient(
        [_gap_evaluation("What were the actual numbers behind that tradeoff?")]
    )
    service = _make_service(llm)
    await service.plan_repo.add(_make_plan())
    interview_id, initial_state = await service.start("job-1")
    original_text = initial_state.current_question_text

    result = await service.submit_answer(interview_id, "I balanced two competing concerns.")

    assert result.current_question_id == "q1"  # still on q1 - a follow-up was asked
    assert result.current_question_text != original_text
    assert result.current_question_text == "What were the actual numbers behind that tradeoff?"
    last_turn = result.history[-1]
    assert last_turn["evaluation"]["decision"] == "follow_up"
    assert last_turn["evaluation"]["weaknesses"] == [
        "A specific metric/number mentioned was never actually given."
    ]


async def test_same_gap_does_not_trigger_unlimited_follow_ups():
    """Test E: a second consecutive gap-shaped evaluation on the same question must not
    produce a second follow-up - the one-follow-up cap forces an advance regardless of the
    evidence, so the loop is always bounded."""
    llm = _ScriptedEvaluationClient(
        [
            _gap_evaluation("What were the actual numbers behind that tradeoff?"),
            _gap_evaluation("Still missing a number - what was it, specifically?"),
        ]
    )
    service = _make_service(llm)
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    follow_up = await service.submit_answer(interview_id, "I balanced two competing concerns.")
    assert follow_up.current_question_id == "q1"

    advanced = await service.submit_answer(interview_id, "Still no numbers, sorry.")
    assert advanced.current_question_id == "q2"  # capped -> advanced, not a second follow-up
    assert advanced.history[-1]["evaluation"]["decision"] == "advance"


async def test_follow_up_is_stored_in_history_and_asked_question_ids_with_a_stable_id():
    """Test F: a follow-up is a first-class, auditable interview turn - it gets its own
    distinct, stable id, recorded in `asked_question_ids` exactly like a planned question, and
    every history turn records which follow-up (if any) it belongs to."""
    llm = _ScriptedEvaluationClient(
        [
            _gap_evaluation("What were the actual numbers behind that tradeoff?"),
            AnswerEvaluation(
                score=0.9,
                evidence_type=AnswerEvidenceType.DEMONSTRATED,
                decision=EvaluationDecision.ADVANCE,
                strengths=["Gave the specific numbers requested."],
                follow_up_needed=False,
            ),
        ]
    )
    service = _make_service(llm)
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    await service.submit_answer(interview_id, "I balanced two competing concerns.")
    result = await service.submit_answer(interview_id, "It was 40ms before, 12ms after.")

    # Test G: the follow-up resolved and the interview genuinely advanced afterward.
    assert result.current_question_id == "q2"
    assert result.asked_question_ids[0] == "q1"
    assert result.asked_question_ids[-1] == "q2"
    assert len(result.asked_question_ids) == 3  # q1, the follow-up, q2
    follow_up_id = result.asked_question_ids[1]
    assert follow_up_id not in ("q1", "q2", "q3")  # a distinct id, not a planned question's

    # Stable: re-deriving the same follow-up (same parent question, same index) reproduces the
    # same id - not a fresh uuid4() each time.
    from app.agents.interview_graph import _follow_up_question_id

    assert follow_up_id == _follow_up_question_id("q1", 0)

    turns = result.history
    assert turns[0]["question_id"] == "q1"
    assert turns[0]["question"] == "Q1?"
    assert turns[0].get("root_question_id") == "q1"

    assert turns[1]["question_id"] == follow_up_id
    assert turns[1]["question"] == "What were the actual numbers behind that tradeoff?"
    assert turns[1]["answer"] == "It was 40ms before, 12ms after."
    assert turns[1].get("root_question_id") == "q1"


# --- question/history identity regression (follow-up entries were reusing the parent's id
# --- and text - see the bug report this fixes) ------------------------------------------


async def test_regression_1_original_and_follow_up_have_different_ids():
    llm = _ScriptedEvaluationClient(
        [_gap_evaluation("What were the actual numbers?"), _strong_evaluation()]
    )
    service = _make_service(llm)
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    await service.submit_answer(interview_id, "I balanced two competing concerns.")
    result = await service.submit_answer(interview_id, "40ms before, 12ms after.")

    original_id, follow_up_id = (turn["question_id"] for turn in result.history)
    assert original_id == "q1"
    assert follow_up_id != original_id
    assert follow_up_id not in ("q1", "q2", "q3")


async def test_regression_2_original_and_follow_up_are_separate_history_entries():
    llm = _ScriptedEvaluationClient(
        [_gap_evaluation("What were the actual numbers?"), _strong_evaluation()]
    )
    service = _make_service(llm)
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    await service.submit_answer(interview_id, "I balanced two competing concerns.")
    result = await service.submit_answer(interview_id, "40ms before, 12ms after.")

    assert len(result.history) == 2
    assert result.history[0]["answer"] == "I balanced two competing concerns."
    assert result.history[1]["answer"] == "40ms before, 12ms after."


async def test_regression_3_follow_up_history_contains_the_actual_follow_up_text():
    follow_up_text = "What were the actual numbers behind that tradeoff?"
    llm = _ScriptedEvaluationClient([_gap_evaluation(follow_up_text), _strong_evaluation()])
    service = _make_service(llm)
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    await service.submit_answer(interview_id, "I balanced two competing concerns.")
    result = await service.submit_answer(interview_id, "40ms before, 12ms after.")

    assert result.history[0]["question"] == "Q1?"  # the original question, unchanged
    assert result.history[1]["question"] == follow_up_text  # not "Q1?" again


async def test_regression_4_asked_question_ids_contains_both_original_and_follow_up_ids():
    llm = _ScriptedEvaluationClient(
        [_gap_evaluation("What were the actual numbers?"), _strong_evaluation()]
    )
    service = _make_service(llm)
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    await service.submit_answer(interview_id, "I balanced two competing concerns.")
    result = await service.submit_answer(interview_id, "40ms before, 12ms after.")

    follow_up_id = result.history[1]["question_id"]
    assert "q1" in result.asked_question_ids
    assert follow_up_id in result.asked_question_ids


async def test_regression_7_completed_interview_with_follow_ups_has_no_duplicate_history_ids():
    llm = _ScriptedEvaluationClient(
        [
            _gap_evaluation("What were the actual numbers?"),
            _strong_evaluation(),
            _gap_evaluation("Can you clarify the second part?"),
            _strong_evaluation(),
            _strong_evaluation(),
        ]
    )
    service = _make_service(llm)
    plan = _make_plan()  # q1, q2, q3
    await service.plan_repo.add(plan)
    interview_id, _ = await service.start("job-1")

    # q1 -> follow-up -> q2 -> follow-up -> q3 -> completed
    await service.submit_answer(interview_id, "I balanced two competing concerns.")
    await service.submit_answer(interview_id, "40ms before, 12ms after.")
    await service.submit_answer(interview_id, "It depends on the situation.")
    await service.submit_answer(interview_id, "Specifically, it was X because Y.")
    finished = await service.submit_answer(interview_id, DETAILED_ANSWER)

    assert finished.status == InterviewStatus.COMPLETED
    history_ids = [turn["question_id"] for turn in finished.history]
    assert len(history_ids) == len(set(history_ids))  # every turn has its own distinct id
    assert len(history_ids) == 5  # q1, its follow-up, q2, its follow-up, q3


async def test_regression_8_existing_no_follow_up_interview_is_unaffected():
    """A question that never gets a follow-up must keep exactly its pre-fix shape: its own id
    both as `question_id` and `root_question_id`, its own text."""
    service = _make_service()
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    result = await service.submit_answer(interview_id, DETAILED_ANSWER)

    assert len(result.history) == 1
    turn = result.history[0]
    assert turn["question_id"] == "q1"
    assert turn["question"] == "Q1?"
    assert turn.get("root_question_id") == "q1"
    assert result.current_question_id == "q2"


async def test_interview_finishes_correctly_after_planned_questions_and_follow_ups():
    """Test H: a follow-up along the way must not prevent the interview from completing
    exactly once every planned question has been asked (and, where triggered, followed up
    on)."""
    llm = _ScriptedEvaluationClient(
        [
            _gap_evaluation("What were the actual numbers?"),
            _strong_evaluation(),
            _strong_evaluation(),
            _strong_evaluation(),
        ]
    )
    service = _make_service(llm)
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    await service.submit_answer(interview_id, "I balanced two competing concerns.")  # -> follow-up
    await service.submit_answer(interview_id, "It was 40ms before, 12ms after.")  # -> q2
    await service.submit_answer(interview_id, DETAILED_ANSWER)  # -> q3
    finished = await service.submit_answer(interview_id, DETAILED_ANSWER)  # -> completed

    assert finished.status == InterviewStatus.COMPLETED
    assert finished.current_question_id is None


async def test_concurrency_still_serializes_correctly_with_a_follow_up_in_play():
    """Test I: concurrency protection must keep working when a follow-up is involved, not just
    on the plain advance path already covered by `test_concurrent_submissions_serialize_
    without_corruption`."""
    llm = _ScriptedEvaluationClient(
        [
            _gap_evaluation("What were the actual numbers?"),
            _strong_evaluation(),
        ]
    )
    service = _make_service(llm)
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    # Two concurrent submissions racing to answer q1 - only one can actually be evaluated
    # against q1 first; the lock must serialize them rather than corrupt state or crash.
    results = await asyncio.gather(
        service.submit_answer(interview_id, "I balanced two competing concerns."),
        service.submit_answer(interview_id, "I balanced two competing concerns."),
    )
    final = await service.get_state(interview_id)
    assert len(set(final.asked_question_ids)) == len(final.asked_question_ids)  # no duplicates
    assert all(r.current_question_id in ("q1", "q2", None) for r in results)


# --- evaluator context regression: a follow-up answer must be evaluated against the
# --- follow-up's own question text, not the parent's (final M4 correctness pass) -----------


def _question_line(input_text: str) -> str:
    """The `QUESTION:` line an `AnswerEvaluationService.evaluate()` call actually sent."""
    return next(line for line in input_text.splitlines() if line.startswith("QUESTION:"))


async def test_regression_A_original_answer_evaluation_receives_original_question_text():
    llm = _ScriptedEvaluationClient([_strong_evaluation()])
    service = _make_service(llm)
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    await service.submit_answer(interview_id, DETAILED_ANSWER)

    assert len(llm.calls) == 1
    assert _question_line(llm.calls[0]) == "QUESTION: Q1?"


async def test_regression_B_follow_up_answer_evaluation_receives_follow_up_question_text():
    follow_up_text = "What were the actual numbers behind that tradeoff?"
    llm = _ScriptedEvaluationClient([_gap_evaluation(follow_up_text), _strong_evaluation()])
    service = _make_service(llm)
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    await service.submit_answer(interview_id, "I balanced two competing concerns.")
    await service.submit_answer(interview_id, "40ms before, 12ms after.")

    assert len(llm.calls) == 2
    assert _question_line(llm.calls[1]) == f"QUESTION: {follow_up_text}"


async def test_regression_C_follow_up_evaluation_does_not_receive_the_parent_question_text():
    follow_up_text = "What were the actual numbers behind that tradeoff?"
    llm = _ScriptedEvaluationClient([_gap_evaluation(follow_up_text), _strong_evaluation()])
    service = _make_service(llm)
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    await service.submit_answer(interview_id, "I balanced two competing concerns.")
    await service.submit_answer(interview_id, "40ms before, 12ms after.")

    # The first call (the original turn) legitimately used the root text - only the second
    # (follow-up) call must not repeat it.
    assert _question_line(llm.calls[0]) == "QUESTION: Q1?"
    assert _question_line(llm.calls[1]) != "QUESTION: Q1?"
    assert "Q1?" not in llm.calls[1]


async def test_regression_D_root_question_id_is_still_preserved():
    llm = _ScriptedEvaluationClient(
        [_gap_evaluation("What were the actual numbers?"), _strong_evaluation()]
    )
    service = _make_service(llm)
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    await service.submit_answer(interview_id, "I balanced two competing concerns.")
    result = await service.submit_answer(interview_id, "40ms before, 12ms after.")

    original_turn, follow_up_turn = result.history
    assert original_turn.get("root_question_id") == "q1"
    assert follow_up_turn.get("root_question_id") == "q1"
    assert follow_up_turn["question_id"] != "q1"  # the follow-up's own id, distinct from root


async def test_regression_E_history_still_has_distinct_ids_and_texts():
    follow_up_text = "What were the actual numbers behind that tradeoff?"
    llm = _ScriptedEvaluationClient([_gap_evaluation(follow_up_text), _strong_evaluation()])
    service = _make_service(llm)
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    await service.submit_answer(interview_id, "I balanced two competing concerns.")
    result = await service.submit_answer(interview_id, "40ms before, 12ms after.")

    original_turn, follow_up_turn = result.history
    assert original_turn["question_id"] != follow_up_turn["question_id"]
    assert original_turn["question"] == "Q1?"
    assert follow_up_turn["question"] == follow_up_text


async def test_regression_F_report_grouping_still_works():
    from app.services.report_scoring import build_competency_assessments, build_question_evaluations

    follow_up_text = "What were the actual numbers behind that tradeoff?"
    llm = _ScriptedEvaluationClient(
        [
            _gap_evaluation(follow_up_text),
            AnswerEvaluation(
                score=0.9,
                evidence_type=AnswerEvidenceType.DEMONSTRATED,
                decision=EvaluationDecision.ADVANCE,
                strengths=["Gave the specific numbers."],
                follow_up_needed=False,
            ),
        ]
    )
    service = _make_service(llm)
    plan = _make_plan()
    await service.plan_repo.add(plan)
    interview_id, _ = await service.start("job-1")

    await service.submit_answer(interview_id, "I balanced two competing concerns.")
    result = await service.submit_answer(interview_id, "40ms before, 12ms after.")

    evaluations = build_question_evaluations(plan, result)
    assert len(evaluations) == 1  # one summary for q1, not two
    assert evaluations[0].question == follow_up_text
    assert evaluations[0].score == pytest.approx(0.9)

    competencies = build_competency_assessments(evaluations)
    assert len(competencies) == 1
    assert competencies[0].name == "A"  # q1's target, from _make_plan()
    assert competencies[0].score == pytest.approx(0.9)


async def test_regression_G_no_follow_up_interview_behaves_exactly_as_before():
    llm = _ScriptedEvaluationClient(
        [_strong_evaluation(), _strong_evaluation(), _strong_evaluation()]
    )
    service = _make_service(llm)
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    await service.submit_answer(interview_id, DETAILED_ANSWER)
    await service.submit_answer(interview_id, DETAILED_ANSWER)
    finished = await service.submit_answer(interview_id, DETAILED_ANSWER)

    assert finished.status == InterviewStatus.COMPLETED
    assert [_question_line(c) for c in llm.calls] == [
        "QUESTION: Q1?",
        "QUESTION: Q2?",
        "QUESTION: Q3?",
    ]
    for turn in finished.history:
        assert turn["question_id"] == turn["root_question_id"]


async def test_regression_H_concurrency_behavior_preserved_with_correct_evaluator_context():
    follow_up_text = "What were the actual numbers?"
    llm = _ScriptedEvaluationClient([_gap_evaluation(follow_up_text), _strong_evaluation()])
    service = _make_service(llm)
    await service.plan_repo.add(_make_plan())
    interview_id, _ = await service.start("job-1")

    results = await asyncio.gather(
        service.submit_answer(interview_id, "I balanced two competing concerns."),
        service.submit_answer(interview_id, "40ms before, 12ms after."),
    )
    final = await service.get_state(interview_id)
    assert len(set(final.asked_question_ids)) == len(final.asked_question_ids)
    assert all(r.current_question_id in ("q1", "q2", None) for r in results)
    # Whichever call landed on the follow-up turn, it must have used the follow-up's own text,
    # never the root's - the lock serializes execution, so exactly one of the two scripted
    # calls corresponds to the follow-up and must show the correct context.
    assert any(_question_line(c) == f"QUESTION: {follow_up_text}" for c in llm.calls)
