"""Regression tests: follow-up questions must be grounded in what the candidate's answer
actually described, not generated from the target name (see the adaptive-interviewer review).
"""

from __future__ import annotations

from app.domain.evaluation import EvaluationDecision
from app.llm.fake_client import FakeLLMClient
from app.services.answer_evaluation import AnswerEvaluationService

PERFORMANCE_ANSWER = (
    "We had a slow endpoint because of an inefficient database query. I added an index and "
    "reduced response time from several seconds to under one second."
)
LEADERSHIP_ANSWER = (
    "I led the rollout of a new deployment pipeline, working with two other engineers to "
    "split up the migration steps across services."
)
BUILD_ANSWER = (
    "I designed a small internal tool that let support staff look up order history without "
    "going through engineering, using a simple form backed by a read replica."
)
GENERIC_SUBSTANTIVE_ANSWER = (
    "I spent a few weeks helping the team move our test suite over to a new framework, "
    "working through each module one at a time until everything passed again."
)


async def _evaluate(answer: str, *, category: str = "technology", target: str = "SQL"):
    service = AnswerEvaluationService(llm=FakeLLMClient())
    return await service.evaluate(
        question_text=f"Tell me about a project where you used {target}.",
        category=category,
        target=target,
        answer=answer,
    )


async def test_no_experience_answer_does_not_trigger_a_generic_example_request():
    """The exact bug from the product review: "I know nothing about SQL" must never produce
    "Can you give a specific example related to SQL?"."""
    result = await _evaluate("I know nothing about SQL.", target="SQL")
    assert result.decision == EvaluationDecision.ADVANCE
    assert result.follow_up_question is None


async def test_a_detailed_answer_can_trigger_a_targeted_follow_up():
    result = await _evaluate(PERFORMANCE_ANSWER, target="SQL")
    assert result.decision == EvaluationDecision.FOLLOW_UP
    assert result.follow_up_question


async def test_follow_up_never_just_restates_the_target_name():
    """Reject the old default mechanism: "Can you give a specific example related to
    {target}?" / "Tell me more about {target}." / "Let's explore that further." must not be
    the follow-up for a substantive, content-rich answer - only for a genuinely vague one."""
    result = await _evaluate(PERFORMANCE_ANSWER, target="SQL")
    assert result.follow_up_question is not None
    lowered = result.follow_up_question.lower()
    assert "sql" not in lowered
    assert lowered != "let's explore that further."
    assert "give a specific example" not in lowered


async def test_follow_up_content_differs_by_answer_content_not_just_target():
    """Two different substantive answers to the *same* target must not collapse to the same
    generic follow-up - the follow-up must reflect what was actually described."""
    performance = await _evaluate(PERFORMANCE_ANSWER, target="SQL")
    leadership = await _evaluate(LEADERSHIP_ANSWER, target="SQL")
    build = await _evaluate(BUILD_ANSWER, target="SQL")

    assert performance.follow_up_question != leadership.follow_up_question
    assert performance.follow_up_question != build.follow_up_question
    assert leadership.follow_up_question != build.follow_up_question


async def test_performance_shaped_answer_gets_a_verification_focused_follow_up():
    result = await _evaluate(PERFORMANCE_ANSWER, target="SQL")
    lowered = result.follow_up_question.lower()
    assert "verify" in lowered or "identify" in lowered


async def test_leadership_shaped_answer_gets_a_people_focused_follow_up():
    result = await _evaluate(
        LEADERSHIP_ANSWER, category="competency", target="Leadership"
    )
    assert result.decision == EvaluationDecision.FOLLOW_UP
    lowered = result.follow_up_question.lower()
    assert "leadership" not in lowered


async def test_generic_substantive_answer_still_gets_a_content_grounded_fallback_follow_up():
    result = await _evaluate(GENERIC_SUBSTANTIVE_ANSWER, target="SQL")
    assert result.decision == EvaluationDecision.FOLLOW_UP
    assert result.follow_up_question
    assert "sql" not in result.follow_up_question.lower()
