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

from app.domain.evaluation import AnswerEvidenceType, EvaluationDecision
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


async def _evaluate(
    answer: str,
    *,
    category: str = "technology",
    target: str = "Python",
    other_targets: list[tuple[str, str]] = (),
):
    service = AnswerEvaluationService(llm=FakeLLMClient())
    return await service.evaluate(
        question_text=f"Tell me about a project where you used {target}.",
        category=category,
        target=target,
        answer=answer,
        other_targets=other_targets,
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


# --- evidence_type: distinguishing WHY an answer is weak, not just THAT it's weak -----------
#
# Real-OpenAI report review finding: a candidate who said "I don't remember, but I remember all
# of my project using MATLAB and C++ language" (asked about Java) was reported as "the candidate
# did not demonstrate experience with Java" - technically defensible, but it reads as a flatter,
# more final claim than what the candidate actually said (an attempted, unverifiable answer, not
# a denial). A different candidate who said "I don't have projects with python, all of my
# projects are around Java and OOP" (asked about Python) explicitly denied the experience -
# genuinely different, and the report must say so differently. These five tests are the
# regression suite requested for that fix: one per required AnswerEvidenceType.


async def test_explicit_lack_of_required_technology():
    """The reported Python case: the candidate explicitly states they don't have the
    experience - the report may accurately say so as a stated fact, not a demonstrated
    deficiency."""
    result = await _evaluate(
        "I don't have projects with Python, all of my projects are around Java and OOP.",
        category="technology",
        target="Python",
    )
    assert result.evidence_type == AnswerEvidenceType.EXPLICIT_LACK
    assert result.decision == EvaluationDecision.ADVANCE
    assert result.follow_up_needed is False
    assert result.strengths == []
    weakness = " ".join(result.weaknesses).lower()
    assert "do not have experience" in weakness or "not have experience" in weakness


async def test_claimed_experience_without_supporting_detail():
    """The reported Java case: the candidate attempts an answer but can't recall/verify enough
    to substantiate it - this must NOT be reported the same way as an explicit denial (the
    candidate never said they lack Java experience)."""
    result = await _evaluate(
        "I don't remember, but I remember all of my project using MATLAB and C++ language.",
        category="technology",
        target="Java",
    )
    assert result.evidence_type == AnswerEvidenceType.CLAIMED_UNVERIFIED
    assert result.evidence_type != AnswerEvidenceType.EXPLICIT_LACK
    assert result.strengths == []  # never credited as evidence of Java specifically
    weakness = " ".join(result.weaknesses).lower()
    assert "did not demonstrate experience" not in weakness  # the exact reported bug phrase
    assert "do not have" not in weakness and "lacks" not in weakness
    assert "verif" in weakness or "could not provide" in weakness


async def test_partial_evidence_leaves_a_follow_up_worthy_gap():
    result = await _evaluate(
        "I used our CI pipeline to automate deployments and fixed a flaky test that was "
        "blocking releases for the team.",
        category="technology",
        target="CI/CD",
    )
    assert result.evidence_type == AnswerEvidenceType.PARTIAL
    assert result.decision == EvaluationDecision.FOLLOW_UP
    assert 0.35 <= result.score < 0.8


async def test_strong_evidence_is_demonstrated():
    result = await _evaluate(DETAILED_PYTHON_ANSWER)
    assert result.evidence_type == AnswerEvidenceType.DEMONSTRATED
    assert result.score >= 0.8
    assert result.strengths


async def test_contradictory_or_inconclusive_answer():
    result = await _evaluate(
        "I have three years of experience with Java, but I've never actually written any "
        "Java code myself.",
        category="technology",
        target="Java",
    )
    assert result.evidence_type == AnswerEvidenceType.CONTRADICTORY
    assert result.strengths == []
    weakness = " ".join(result.weaknesses).lower()
    assert "inconsistent" in weakness


# --- cross-target evidence: an answer can volunteer evidence about a DIFFERENT target than
# --- the one actually asked about (Copilot review) - see app.services.cross_target_evidence
# --- for how the interview graph resolves this; these tests only cover the evaluator's own
# --- classification of it, through the real FakeLLMClient code path (not a private helper).


async def test_strong_incidental_mention_of_another_target_is_reported_as_demonstrated():
    result = await _evaluate(
        "I built a Python microservice using FastAPI and deployed it to production. I also "
        "have extensive Java experience, having built and maintained several production "
        "services with it.",
        category="technology",
        target="Python",
        other_targets=[("technology", "Java")],
    )
    assert len(result.cross_target_evidence) == 1
    java_evidence = result.cross_target_evidence[0]
    assert java_evidence.target == "Java"
    assert java_evidence.evidence_type == AnswerEvidenceType.DEMONSTRATED


async def test_casual_mention_of_another_target_is_reported_as_claimed_unverified():
    """A bare namedrop must never be inflated into strong evidence - see the classification
    rule this exists to enforce."""
    result = await _evaluate(
        "I built a Python microservice using FastAPI and deployed it to production. I've "
        "also used Java a little bit.",
        category="technology",
        target="Python",
        other_targets=[("technology", "Java")],
    )
    assert len(result.cross_target_evidence) == 1
    java_evidence = result.cross_target_evidence[0]
    assert java_evidence.evidence_type != AnswerEvidenceType.DEMONSTRATED
    assert java_evidence.evidence_type == AnswerEvidenceType.CLAIMED_UNVERIFIED


async def test_no_mention_of_other_targets_produces_no_cross_target_evidence():
    result = await _evaluate(
        DETAILED_PYTHON_ANSWER,
        other_targets=[("technology", "Java"), ("technology", "Go")],
    )
    assert result.cross_target_evidence == []


async def test_explicit_lack_of_the_current_target_never_invents_evidence_for_another():
    """The reported failure mode this must never regress into: an explicit denial about the
    target actually asked about must not be reinterpreted as evidence - of any kind - about a
    completely different, unmentioned target."""
    result = await _evaluate(
        "I don't have experience with this.",
        category="technology",
        target="Python",
        other_targets=[("technology", "Java")],
    )
    assert result.evidence_type == AnswerEvidenceType.EXPLICIT_LACK
    assert result.cross_target_evidence == []


async def test_cross_target_classification_is_deterministic():
    kwargs = dict(
        answer=(
            "I built a Python microservice using FastAPI and deployed it to production. I "
            "also have extensive Java experience, having built several production services."
        ),
        category="technology",
        target="Python",
        other_targets=[("technology", "Java")],
    )
    first = await _evaluate(**kwargs)
    second = await _evaluate(**kwargs)
    assert first.cross_target_evidence == second.cross_target_evidence


# --- Real-run verification cases (PostgreSQL/RESTful APIs): the exact scenarios from the
# --- adaptive-runtime review, using their literal wording, to pin down the cross-target
# --- evidence contract end to end through the real AnswerEvaluationService/FakeLLMClient path.


async def test_case_A_strong_direct_evidence_for_the_asked_target():
    # DETAILED_PYTHON_ANSWER is the same "used Python extensively with FastAPI to build
    # backend services" claim as the reviewed real interview, with enough concrete detail to
    # clear the fake client's substantive-answer bar (a bare, much shorter version of the same
    # claim is exactly what test_unsupported_claims_are_never_scored_as_strong_evidence exists
    # to keep from being scored this well).
    result = await _evaluate(DETAILED_PYTHON_ANSWER, category="technology", target="Python")
    assert result.evidence_type == AnswerEvidenceType.DEMONSTRATED
    assert result.decision == EvaluationDecision.ADVANCE
    assert result.score >= 0.8


async def test_case_B_strong_evidence_for_a_different_required_target():
    result = await _evaluate(
        "For persistence, I used PostgreSQL with SQLAlchemy and designed normalized schemas.",
        category="technology",
        target="RESTful APIs",
        other_targets=[("technology", "PostgreSQL")],
    )
    # The current answer is about persistence/PostgreSQL, not the asked-about RESTful APIs -
    # it must not be credited as strong evidence of the target actually asked about.
    assert result.evidence_type != AnswerEvidenceType.DEMONSTRATED
    # PostgreSQL, mentioned with real, verb-backed detail, is recognized as cross-target
    # evidence strong enough to resolve it without asking about it again.
    assert len(result.cross_target_evidence) == 1
    postgres_evidence = result.cross_target_evidence[0]
    assert postgres_evidence.target == "PostgreSQL"
    assert postgres_evidence.evidence_type == AnswerEvidenceType.DEMONSTRATED


async def test_case_C_casual_mention_does_not_strongly_assess_the_other_target():
    result = await _evaluate(
        "We used PostgreSQL somewhere in the project.",
        category="technology",
        target="RESTful APIs",
        other_targets=[("technology", "PostgreSQL")],
    )
    assert len(result.cross_target_evidence) == 1
    postgres_evidence = result.cross_target_evidence[0]
    assert postgres_evidence.evidence_type != AnswerEvidenceType.DEMONSTRATED


async def test_case_D_explicit_lack_is_recorded_not_treated_as_covered():
    result = await _evaluate(
        "I haven't worked with PostgreSQL.",
        category="technology",
        target="RESTful APIs",
        other_targets=[("technology", "PostgreSQL")],
    )
    assert len(result.cross_target_evidence) == 1
    postgres_evidence = result.cross_target_evidence[0]
    assert postgres_evidence.target == "PostgreSQL"
    assert postgres_evidence.evidence_type == AnswerEvidenceType.EXPLICIT_LACK
    # Explicit lack is conclusive (nothing further to probe) but is never the same claim as
    # "successfully covered/demonstrated" - see app.services.cross_target_evidence.
    assert postgres_evidence.evidence_type != AnswerEvidenceType.DEMONSTRATED


async def test_case_E_unrelated_evidence_for_a_different_technology_question():
    result = await _evaluate(
        "I used PostgreSQL for persistence.",
        category="technology",
        target="Python",
        other_targets=[("technology", "PostgreSQL")],
    )
    # Python (the actual question) is not considered covered by an answer that's entirely
    # about a different technology.
    assert result.evidence_type != AnswerEvidenceType.DEMONSTRATED
    assert result.score < 0.8
