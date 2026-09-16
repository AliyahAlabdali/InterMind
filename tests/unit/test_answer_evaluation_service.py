import pytest

from app.domain.evaluation import AnswerEvaluation, EvaluationDecision
from app.llm.fake_client import FakeLLMClient
from app.services.answer_evaluation import AnswerEvaluationService


async def test_evaluate_detailed_answer_advances():
    service = AnswerEvaluationService(llm=FakeLLMClient())
    result = await service.evaluate(
        question_text="Tell me about a time you demonstrated ownership.",
        category="competency",
        target="Ownership",
        answer=(
            "I noticed a recurring production bug, tracked it to a race condition in the "
            "queue consumer, fixed it, and added a regression test."
        ),
    )
    assert isinstance(result, AnswerEvaluation)
    assert result.decision == EvaluationDecision.ADVANCE
    assert result.follow_up_needed is False
    assert result.follow_up_question is None
    assert result.evidence


async def test_evaluate_short_answer_requests_follow_up():
    service = AnswerEvaluationService(llm=FakeLLMClient())
    result = await service.evaluate(
        question_text="Tell me about a time you demonstrated ownership.",
        category="competency",
        target="Ownership",
        answer="I fixed a bug once.",
    )
    assert result.decision == EvaluationDecision.FOLLOW_UP
    assert result.follow_up_needed is True
    assert result.follow_up_question is not None
    assert "ownership" in result.follow_up_question.lower()


async def test_evaluate_empty_answer_requests_follow_up():
    service = AnswerEvaluationService(llm=FakeLLMClient())
    result = await service.evaluate(
        question_text="Tell me about a time you demonstrated ownership.",
        category="competency",
        target="Ownership",
        answer="   ",
    )
    assert result.decision == EvaluationDecision.FOLLOW_UP
    assert result.follow_up_needed is True


async def test_evaluate_uses_configured_fake_response():
    canned = AnswerEvaluation(
        score=0.95,
        decision=EvaluationDecision.ADVANCE,
        strengths=["Clear, specific example."],
        weaknesses=[],
        evidence=["fixed a race condition"],
        follow_up_needed=False,
    )
    service = AnswerEvaluationService(llm=FakeLLMClient(response=canned))
    result = await service.evaluate(
        question_text="anything",
        category="competency",
        target="Ownership",
        answer="anything",
    )
    assert result == canned


def test_decision_authoritative_over_follow_up_needed():
    """`decision` is authoritative over `follow_up_needed` - the two are reconciled so they
    never contradict."""
    evaluation = AnswerEvaluation(
        score=0.9,
        decision=EvaluationDecision.ADVANCE,
        follow_up_needed=True,
        follow_up_question="Kept - see below.",
    )
    assert evaluation.follow_up_needed is False


def test_follow_up_question_survives_an_advance_decision():
    """Unlike `follow_up_needed`, `follow_up_question` is deliberately *not* nulled just
    because `decision` is `advance` - the system's own follow-up policy
    (`resolve_follow_up_decision`) may still use it as signal, independent of the model's own
    one-shot `decision` guess (see that function's docstring for the real bug this fixes: a
    real LLM under-calling a follow-up it had otherwise correctly identified)."""
    evaluation = AnswerEvaluation(
        score=0.9,
        decision=EvaluationDecision.ADVANCE,
        follow_up_needed=True,
        follow_up_question="A concrete, answer-grounded question.",
    )
    assert evaluation.follow_up_question == "A concrete, answer-grounded question."


@pytest.mark.parametrize("score", [-0.1, 1.1])
def test_score_out_of_range_rejected(score):
    with pytest.raises(ValueError):
        AnswerEvaluation(
            score=score,
            decision=EvaluationDecision.ADVANCE,
            follow_up_needed=False,
        )
