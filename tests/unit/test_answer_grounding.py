"""Adversarial/anti-gaming regression tests for answer evaluation.

Milestone review finding: a pure word-count heuristic scored "I don't know anything about
Python, is that a snake?" as strong evidence of Python proficiency, because it never looked at
what the words actually said. These tests pin down the rule that must never regress: the
question/target is context for what to assess, never evidence that the candidate demonstrated
it - only the candidate's own words are evidence. Exercised through
:class:`AnswerEvaluationService` + :class:`FakeLLMClient` together (the actual code path used
without a real LLM key), not by calling private helpers directly.
"""

from __future__ import annotations

import pytest

from app.domain.evaluation import EvaluationDecision
from app.llm.fake_client import FakeLLMClient
from app.services.answer_evaluation import AnswerEvaluationService

NO_EVIDENCE_ANSWERS = [
    "I don't know.",
    "I don't have experience with this.",
    "Is Python a snake?",
    "I haven't used Python.",
    "I only used Java.",
    "I know nothing about Python, is that a snake?",
]

UNSUPPORTED_CLAIM_ANSWERS = [
    "Python is my favorite language.",
    "I have ten years of Python experience.",
]

DETAILED_PYTHON_ANSWER = (
    "I used Python extensively to build a FastAPI backend service, writing async endpoints, "
    "integrating with PostgreSQL via SQLAlchemy, and adding unit tests with pytest for the "
    "core business logic."
)


async def _evaluate(answer: str, *, category: str = "technology", target: str = "Python"):
    service = AnswerEvaluationService(llm=FakeLLMClient())
    return await service.evaluate(
        question_text=f"Tell me about a project where you used {target}.",
        category=category,
        target=target,
        answer=answer,
    )


@pytest.mark.parametrize("answer", NO_EVIDENCE_ANSWERS)
async def test_explicit_no_evidence_answers_never_score_as_strong(answer):
    result = await _evaluate(answer)
    assert result.score < 0.35
    assert result.decision == EvaluationDecision.ADVANCE
    assert result.strengths == []


@pytest.mark.parametrize("answer", NO_EVIDENCE_ANSWERS)
async def test_explicit_no_evidence_does_not_ask_for_an_example_they_said_they_lack(answer):
    """The specific bug from the product review: asking "can you give a specific example" of
    something the candidate just said they don't have. An explicit lack-of-experience answer
    must advance, not trigger a follow-up requesting an example."""
    result = await _evaluate(answer)
    assert result.follow_up_needed is False
    assert result.follow_up_question is None


@pytest.mark.parametrize("answer", NO_EVIDENCE_ANSWERS)
async def test_explicit_no_evidence_weakness_never_claims_incapability(answer):
    """"Did not demonstrate X" is defensible from one answer; "lacks X" / "is incapable of X"
    is not - the report must communicate uncertainty honestly (see the report-quality review)."""
    result = await _evaluate(answer)
    for text in result.weaknesses:
        lowered = text.lower()
        assert "lacks" not in lowered
        assert "incapable" not in lowered
        assert "is weak at" not in lowered


@pytest.mark.parametrize("answer", UNSUPPORTED_CLAIM_ANSWERS)
async def test_unsupported_claims_are_never_scored_as_strong_evidence(answer):
    """A bare claim ("ten years of experience", "my favorite language") with no supporting
    detail must not be classified as strong evidence just because it names the target."""
    result = await _evaluate(answer)
    assert result.score < 0.8


async def test_detailed_answer_produces_appropriate_strong_evidence():
    result = await _evaluate(DETAILED_PYTHON_ANSWER)
    assert result.score >= 0.8
    assert result.decision == EvaluationDecision.ADVANCE
    assert result.strengths


@pytest.mark.parametrize("answer", NO_EVIDENCE_ANSWERS + UNSUPPORTED_CLAIM_ANSWERS)
async def test_target_name_never_appears_as_fabricated_evidence(answer):
    """`evidence` may quote the candidate's own answer, but must never be padded with the bare
    target name as if repeating it back were proof of anything."""
    result = await _evaluate(answer)
    for item in result.evidence:
        assert item.strip().lower() != "python"


# --- the same rule for a competency and a task target, not just technology -----------------


async def test_no_evidence_rule_applies_to_a_competency_target():
    result = await _evaluate(
        "I don't have experience leading a team.", category="competency", target="Leadership"
    )
    assert result.score < 0.35
    assert result.decision == EvaluationDecision.ADVANCE
    assert result.strengths == []


async def test_detailed_answer_scores_well_for_a_competency_target():
    result = await _evaluate(
        "I led a cross-functional initiative to migrate our checkout flow, coordinating "
        "three engineers and a designer, and mentored two junior developers through the "
        "rollout.",
        category="competency",
        target="Leadership",
    )
    assert result.score >= 0.8
    assert result.decision == EvaluationDecision.ADVANCE


async def test_no_evidence_rule_applies_to_a_task_target():
    result = await _evaluate(
        "I've never done anything like that.",
        category="task",
        target="Operate biomass fuel-burning boiler equipment.",
    )
    assert result.score < 0.35
    assert result.decision == EvaluationDecision.ADVANCE
    assert result.strengths == []
