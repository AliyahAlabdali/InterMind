from pydantic import BaseModel

from app.core.exceptions import LLMError
from app.domain.interview import InterviewState, InterviewStatus
from app.domain.interview_plan import (
    InterviewPlan,
    InterviewQuestion,
    QuestionCategory,
)
from app.domain.occupation import OccupationMatch
from app.domain.report import Recommendation
from app.llm.fake_client import FakeLLMClient
from app.services.report_generation import ReportGenerationService
from app.services.report_narrative import ReportNarrativeService


class _AlwaysFailingLLMClient:
    async def generate_structured(self, *, prompt, input_text, schema: type[BaseModel]):
        raise LLMError("upstream provider exploded with a secret-bearing message: sk-XYZ")


def _plan() -> InterviewPlan:
    return InterviewPlan(
        job_id="job-1",
        occupation_match=OccupationMatch(
            onet_soc_code="15-1252.00", title="Software Developers", score=1.0
        ),
        questions=[
            InterviewQuestion(
                id="q1",
                category=QuestionCategory.COMPETENCY,
                text="Q1?",
                target="Ownership",
                grounding="g",
            ),
        ],
    )


def _completed_state(score: float, decision: str) -> InterviewState:
    return InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["q1"],
        history=[
            {
                "question_id": "q1",
                "question": "Q1?",
                "answer": "a detailed answer with a concrete example",
                "evaluation": {
                    "score": score,
                    "decision": decision,
                    "strengths": ["Gave a concrete example"],
                    "weaknesses": [],
                    "evidence": ["a detailed answer with a concrete example"],
                    "follow_up_needed": False,
                    "follow_up_question": None,
                },
            }
        ],
    )


async def test_generate_happy_path_with_fake_llm():
    service = ReportGenerationService(narrative=ReportNarrativeService(llm=FakeLLMClient()))
    report = await service.generate(
        interview_id="i1", plan=_plan(), state=_completed_state(0.8, "advance")
    )

    assert report.interview_id == "i1"
    assert report.job_id == "job-1"
    assert report.overall_score == 0.8
    assert report.recommendation == Recommendation.HIRE
    assert len(report.question_evaluations) == 1
    assert len(report.competencies) == 1
    assert report.summary  # non-empty


async def test_llm_failure_does_not_corrupt_deterministic_scoring():
    failing_narrative = ReportNarrativeService(llm=_AlwaysFailingLLMClient())
    service = ReportGenerationService(narrative=failing_narrative)

    report = await service.generate(
        interview_id="i1", plan=_plan(), state=_completed_state(0.8, "advance")
    )

    # Deterministic fields are unaffected by the narrative LLM failing outright.
    assert report.overall_score == 0.8
    assert report.recommendation == Recommendation.HIRE
    assert len(report.question_evaluations) == 1
    assert report.question_evaluations[0].score == 0.8

    # A usable fallback narrative is still produced - the report generation call didn't fail.
    assert report.summary
    assert "0.80" in report.summary
    assert report.strengths == ["Gave a concrete example"]

    # No secret/raw provider detail leaked into the report from the failed LLM call.
    assert "sk-XYZ" not in report.summary
    assert all("sk-XYZ" not in s for s in report.strengths + report.weaknesses)


async def test_generate_deterministic_fields_stable_across_repeated_calls():
    service = ReportGenerationService(narrative=ReportNarrativeService(llm=FakeLLMClient()))
    state = _completed_state(0.8, "advance")

    first = await service.generate(interview_id="i1", plan=_plan(), state=state)
    second = await service.generate(interview_id="i1", plan=_plan(), state=state)

    assert first.overall_score == second.overall_score
    assert first.recommendation == second.recommendation
    assert first.competencies == second.competencies
    assert first.question_evaluations == second.question_evaluations
