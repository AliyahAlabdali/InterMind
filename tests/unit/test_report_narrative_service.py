from app.domain.interview_plan import QuestionCategory
from app.domain.report import CompetencyAssessment, ReportNarrative
from app.llm.fake_client import FakeLLMClient
from app.services.report_narrative import ReportNarrativeService


def _competency(
    name, category, score, strengths=None, weaknesses=None, evidence=None
) -> CompetencyAssessment:
    return CompetencyAssessment(
        name=name,
        category=category,
        score=score,
        strengths=strengths or [],
        weaknesses=weaknesses or [],
        evidence=evidence or [],
    )


async def test_fake_narrative_only_echoes_given_strengths_and_weaknesses():
    competencies = [
        _competency(
            "Ownership",
            QuestionCategory.COMPETENCY,
            0.8,
            strengths=["Gave a concrete example"],
            weaknesses=[],
        ),
        _competency(
            "Python",
            QuestionCategory.TECHNOLOGY,
            0.3,
            strengths=[],
            weaknesses=["Lacked technical depth"],
        ),
    ]
    service = ReportNarrativeService(llm=FakeLLMClient())
    result = await service.synthesize(
        overall_score=0.6, recommendation="consider", competencies=competencies
    )

    assert isinstance(result, ReportNarrative)
    # No unsupported claims: every returned item must have come from the given input.
    given_strengths = {"Gave a concrete example"}
    given_weaknesses = {"Lacked technical depth"}
    assert set(result.strengths) <= given_strengths
    assert set(result.weaknesses) <= given_weaknesses
    # The summary describes the candidate, never the scoring mechanism or a raw percentage.
    assert "0.60" not in result.summary
    assert "deterministic" not in result.summary.lower()
    assert "consider" in result.summary


async def test_fake_narrative_deterministic_for_identical_input():
    competencies = [
        _competency("Ownership", QuestionCategory.COMPETENCY, 0.8, strengths=["Detailed answer"])
    ]
    service = ReportNarrativeService(llm=FakeLLMClient())

    first = await service.synthesize(
        overall_score=0.8, recommendation="hire", competencies=competencies
    )
    second = await service.synthesize(
        overall_score=0.8, recommendation="hire", competencies=competencies
    )

    assert first == second


async def test_fake_narrative_handles_no_evidence_competency_without_inventing():
    competencies = [_competency("Ownership", QuestionCategory.COMPETENCY, None)]
    service = ReportNarrativeService(llm=FakeLLMClient())
    result = await service.synthesize(
        overall_score=0.0, recommendation="no_hire", competencies=competencies
    )

    assert result.strengths == []
    assert result.weaknesses == []


async def test_synthesize_uses_configured_fake_response():
    canned = ReportNarrative(summary="Canned summary.", strengths=["x"], weaknesses=["y"])
    service = ReportNarrativeService(llm=FakeLLMClient(response=canned))
    result = await service.synthesize(overall_score=0.5, recommendation="consider", competencies=[])
    assert result == canned
