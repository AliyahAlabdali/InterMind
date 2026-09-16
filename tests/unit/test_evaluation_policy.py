"""Tests for `resolve_follow_up_decision` - the deterministic advance/follow-up policy that
replaced trusting the LLM's single-shot `decision` field for routing.

Regression context: a real end-to-end OpenAI test showed the interviewer always advancing even
when the evaluator itself had identified a concrete evidence gap (e.g. a candidate describing a
computer-vision project who mentioned "balancing detection accuracy with inference speed" but
gave no actual numbers) - the evaluator recorded the gap, but the graph's routing never looked
at anything except the model's own `decision` field, which under-called the follow-up. These
tests exercise the policy directly with hand-built `AnswerEvaluation` instances - deliberately
generic (no hard-coded target/category/domain, per the requirement that this behavior must
apply to any interview target) - so they stay fast, deterministic, and fully offline.
"""

from __future__ import annotations

import pytest

from app.domain.evaluation import (
    AnswerEvaluation,
    EvaluationDecision,
    resolve_follow_up_decision,
)

# A generic stand-in for "the candidate described real work but left a specific, worthwhile
# detail unexplored" - deliberately not tied to any particular technology/competency/task, to
# prove the policy is generic (see the module docstring).
GENERIC_FOLLOW_UP_QUESTION = "You mentioned a tradeoff - what were the actual numbers involved?"


def _evaluation(
    *,
    score: float,
    decision: EvaluationDecision = EvaluationDecision.ADVANCE,
    weaknesses: list[str] | None = None,
    follow_up_question: str | None = None,
) -> AnswerEvaluation:
    return AnswerEvaluation(
        score=score,
        decision=decision,
        strengths=["Described a real, specific piece of work."],
        weaknesses=weaknesses or [],
        evidence=["a close paraphrase of the answer"],
        follow_up_needed=decision == EvaluationDecision.FOLLOW_UP,
        follow_up_question=follow_up_question,
    )


# --- A: sufficient evidence -> advance -------------------------------------------------------


def test_strong_evidence_with_no_gap_advances():
    evaluation = _evaluation(score=0.9)
    resolved = resolve_follow_up_decision(evaluation, follow_ups_used=0)
    assert resolved.decision == EvaluationDecision.ADVANCE
    assert resolved.follow_up_question is None


def test_strong_evidence_with_a_follow_up_question_but_no_recorded_weakness_still_advances():
    """A strong, thorough-looking answer that happens to have an optional follow-up question
    attached (but no explicit weakness) should not be second-guessed into a follow-up - the
    strong band requires both signals together (see resolve_follow_up_decision's docstring)."""
    evaluation = _evaluation(score=0.85, follow_up_question=GENERIC_FOLLOW_UP_QUESTION)
    resolved = resolve_follow_up_decision(evaluation, follow_ups_used=0)
    assert resolved.decision == EvaluationDecision.ADVANCE


# --- B: the core bug - strong/moderate evidence with a real, specific gap -> follow-up -------


def test_strong_evidence_with_a_specific_recorded_gap_still_follows_up():
    """The exact reported bug, stated generically: the model can score an answer as strong
    (real, substantive work described) while still identifying one concrete, worthwhile detail
    left unexplored - that must trigger a follow-up, even though `decision` itself might say
    `advance` (a real LLM's one-shot classification proved unreliable here)."""
    evaluation = _evaluation(
        score=0.85,
        decision=EvaluationDecision.ADVANCE,  # the model's own (under-called) guess
        weaknesses=["No specific metric was given for the tradeoff mentioned."],
        follow_up_question=GENERIC_FOLLOW_UP_QUESTION,
    )
    resolved = resolve_follow_up_decision(evaluation, follow_ups_used=0)
    assert resolved.decision == EvaluationDecision.FOLLOW_UP
    assert resolved.follow_up_needed is True
    assert resolved.follow_up_question == GENERIC_FOLLOW_UP_QUESTION
    # The underlying observations are untouched - only the routing fields changed.
    assert resolved.score == 0.85
    assert resolved.weaknesses == evaluation.weaknesses


def test_moderate_evidence_with_a_follow_up_question_triggers_follow_up():
    evaluation = _evaluation(
        score=0.65,
        decision=EvaluationDecision.ADVANCE,
        follow_up_question=GENERIC_FOLLOW_UP_QUESTION,
    )
    resolved = resolve_follow_up_decision(evaluation, follow_ups_used=0)
    assert resolved.decision == EvaluationDecision.FOLLOW_UP


# --- C: insufficient/limited answer -> follow-up or clarification ---------------------------


@pytest.mark.parametrize("score", [0.3, 0.1])
def test_weak_evidence_with_a_follow_up_question_triggers_follow_up_or_clarification(score):
    evaluation = _evaluation(
        score=score,
        decision=EvaluationDecision.FOLLOW_UP,
        follow_up_question="Can you walk through a specific example?",
    )
    resolved = resolve_follow_up_decision(evaluation, follow_ups_used=0)
    assert resolved.decision == EvaluationDecision.FOLLOW_UP


@pytest.mark.parametrize("score", [0.05, 0.3])
def test_weak_evidence_with_no_follow_up_question_advances_instead_of_asking_a_dead_end(score):
    """Anti-gaming rule preserved: an explicit lack-of-experience / off-topic answer has
    nothing concrete to probe (the model is instructed to leave `follow_up_question` empty in
    that case) - the policy must not fabricate a generic follow-up just because evidence is
    weak."""
    evaluation = _evaluation(
        score=score, decision=EvaluationDecision.ADVANCE, follow_up_question=None
    )
    resolved = resolve_follow_up_decision(evaluation, follow_ups_used=0)
    assert resolved.decision == EvaluationDecision.ADVANCE
    assert resolved.follow_up_question is None


def test_a_wants_follow_up_signal_with_blank_follow_up_question_text_does_not_fabricate_one():
    evaluation = _evaluation(
        score=0.3, decision=EvaluationDecision.FOLLOW_UP, follow_up_question="   "
    )
    resolved = resolve_follow_up_decision(evaluation, follow_ups_used=0)
    assert resolved.decision == EvaluationDecision.ADVANCE


# --- D: follow-up is grounded in the evaluation's own signal, not the target ------------------


def test_resolved_follow_up_question_is_exactly_the_evidence_grounded_one_provided():
    """The policy never invents its own follow-up text - it only ever surfaces (or suppresses)
    whatever answer-grounded question the evaluation itself produced."""
    evaluation = _evaluation(
        score=0.7,
        weaknesses=["The tradeoff mentioned was never quantified."],
        follow_up_question=GENERIC_FOLLOW_UP_QUESTION,
    )
    resolved = resolve_follow_up_decision(evaluation, follow_ups_used=0)
    assert resolved.follow_up_question == GENERIC_FOLLOW_UP_QUESTION


# --- E/F: cap reached / already followed up on this target -> advance ------------------------


def test_at_the_follow_up_cap_always_advances_regardless_of_evidence():
    evaluation = _evaluation(
        score=0.2,
        decision=EvaluationDecision.FOLLOW_UP,
        follow_up_question="Can you give a concrete example?",
    )
    resolved = resolve_follow_up_decision(evaluation, follow_ups_used=1, max_follow_ups=1)
    assert resolved.decision == EvaluationDecision.ADVANCE
    assert resolved.follow_up_question is None


def test_a_higher_configured_cap_still_allows_a_second_follow_up():
    evaluation = _evaluation(
        score=0.3,
        decision=EvaluationDecision.FOLLOW_UP,
        follow_up_question="Can you give a concrete example?",
    )
    resolved = resolve_follow_up_decision(evaluation, follow_ups_used=1, max_follow_ups=2)
    assert resolved.decision == EvaluationDecision.FOLLOW_UP
