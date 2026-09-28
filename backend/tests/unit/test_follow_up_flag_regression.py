"""Regression: ``current_question_is_follow_up`` must read the last *asked* turn.

The flag was derived from ``history[-1].question_id == current_question_id``. That holds right
up until one answer does two things at once - answers the question it was asked, and also
establishes some *other* coverage target. The resolver appends a synthesized turn for that
other target (``assessment_method="cross_target"``) after the real one, so ``history[-1]`` is no
longer the turn that was evaluated for the current question, the id comparison fails, and a
genuine follow-up reports itself as a new question.

Observed in a QA run: InterMind was asking a follow-up on Python while the API returned
``current_question_is_follow_up: false``, so the candidate UI silently skipped the beat that
marks a follow-up.

These exercise ``InterviewResponse.from_state`` directly - the flag is derived there, and
nothing about evaluation, routing or report scoring is involved.
"""

from __future__ import annotations

from app.api.schemas import InterviewResponse
from app.domain.interview import InterviewState, InterviewStatus

PYTHON = "python-target-id"
NLP = "nlp-target-id"
FOLLOW_UP = "python-target-id::follow-up-1"


def _asked_turn(question_id: str, decision: str, root: str | None = None) -> dict:
    """A turn for a question actually put to the candidate. Real main-question turns never set
    ``assessment_method`` at all - its absence is what means "direct"."""
    return {
        "question_id": question_id,
        "question": "a question",
        "answer": "an answer",
        "evaluation": {"decision": decision, "score": 0.5},
        "root_question_id": root or question_id,
    }


def _cross_target_turn(target_id: str) -> dict:
    return {
        "question_id": target_id,
        "question": "(Not asked directly - identified from the candidate's answer to a "
        "different question.)",
        "answer": "a quote from the other answer",
        "evaluation": {"decision": "advance", "score": 0.8},
        "root_question_id": target_id,
        "assessment_method": "cross_target",
    }


def _response(history: list[dict], current_question_id: str | None) -> InterviewResponse:
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.IN_PROGRESS,
        current_question_id=current_question_id,
        current_question_text="the question on screen",
        asked_question_ids=[PYTHON],
        history=history,
    )
    return InterviewResponse.from_state(
        interview_id="interview-1",
        state=state,
        candidate_name="Candidate",
        candidate_email="",
    )


def test_a_first_question_is_not_a_follow_up():
    assert _response([], PYTHON).current_question_is_follow_up is False


def test_a_new_target_after_an_advance_is_not_a_follow_up():
    history = [_asked_turn(PYTHON, "advance")]
    assert _response(history, NLP).current_question_is_follow_up is False


def test_a_direct_follow_up_is_reported_as_one():
    """The case that already worked: one turn, decision follow_up, same target still current."""
    history = [_asked_turn(PYTHON, "follow_up")]
    assert _response(history, PYTHON).current_question_is_follow_up is True


def test_a_follow_up_is_still_reported_when_cross_target_evidence_lands_on_the_same_answer():
    """The regression. The cross-target turn is appended *after* the turn that was evaluated,
    and reading the last entry blindly loses the follow-up."""
    history = [_asked_turn(PYTHON, "follow_up"), _cross_target_turn(NLP)]
    assert _response(history, PYTHON).current_question_is_follow_up is True


def test_cross_target_evidence_without_a_follow_up_is_not_reported_as_one():
    """The gate must not become "true whenever a cross-target turn exists"."""
    history = [_asked_turn(PYTHON, "advance"), _cross_target_turn(NLP)]
    assert _response(history, NLP).current_question_is_follow_up is False


def test_several_cross_target_turns_do_not_hide_the_asked_turn():
    history = [
        _asked_turn(PYTHON, "follow_up"),
        _cross_target_turn(NLP),
        _cross_target_turn("another-target-id"),
    ]
    assert _response(history, PYTHON).current_question_is_follow_up is True


def test_moving_on_after_a_follow_up_is_not_itself_a_follow_up():
    """Transition out: the follow-up has been answered and the interview has moved to a new
    target, so the new question must not inherit the flag."""
    history = [
        _asked_turn(PYTHON, "follow_up"),
        _cross_target_turn("another-target-id"),
        _asked_turn(FOLLOW_UP, "advance", root=PYTHON),
    ]
    assert _response(history, NLP).current_question_is_follow_up is False


def test_a_capped_follow_up_that_forced_an_advance_is_not_reported_as_one():
    """Pre-existing behaviour, kept: the one-follow-up cap can leave a turn's decision as
    "follow_up" while the interview has already moved on. The id comparison is what catches
    that, and it must keep catching it now that the turn is found by searching."""
    history = [_asked_turn(FOLLOW_UP, "follow_up", root=PYTHON)]
    assert _response(history, NLP).current_question_is_follow_up is False


def test_a_history_of_only_cross_target_turns_reports_no_follow_up():
    assert _response([_cross_target_turn(NLP)], PYTHON).current_question_is_follow_up is False


def test_no_current_question_reports_no_follow_up():
    history = [_asked_turn(PYTHON, "follow_up")]
    assert _response(history, None).current_question_is_follow_up is False
