from pydantic import BaseModel

from app.core.exceptions import LLMError
from app.domain.interview import InterviewState, InterviewStatus
from app.domain.interview_plan import (
    CoverageTarget,
    EvidenceSource,
    InterviewPlan,
    QuestionCategory,
    RequirementLevel,
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
        role_title="Software Developer",
        occupation_match=OccupationMatch(
            onet_soc_code="15-1252.00", title="Software Developers", score=1.0
        ),
        coverage_targets=[
            CoverageTarget(
                id="q1",
                category=QuestionCategory.COMPETENCY,
                target="Ownership",
                requirement_level=RequirementLevel.REQUIRED,
                source=EvidenceSource.JOBSPEC,
                priority=0,
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
    # The summary describes the candidate's performance in plain language - it must never
    # expose the raw score or the scoring mechanism (see the report-quality review).
    assert "0.80" not in report.summary
    assert "deterministic" not in report.summary.lower()
    assert "hire" in report.summary.lower()
    assert report.strengths == ["Ownership: Gave a concrete example"]

    # No secret/raw provider detail leaked into the report from the failed LLM call.
    assert "sk-XYZ" not in report.summary
    assert all("sk-XYZ" not in s for s in report.strengths + report.weaknesses)


def _weak_completed_state() -> InterviewState:
    """Two questions, both with insufficient evidence for different reasons - one competency
    each so the summary must name both if it names any (see the test below)."""
    return InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["q1", "q2"],
        history=[
            {
                "question_id": "q1",
                "question": "Q1?",
                "answer": "I don't have projects with Python.",
                "evaluation": {
                    "score": 0.05,
                    "decision": "advance",
                    "evidence_type": "explicit_lack",
                    "strengths": [],
                    "weaknesses": ["The candidate stated they do not have experience with Python."],
                    "evidence": [],
                    "follow_up_needed": False,
                    "follow_up_question": None,
                },
            },
            {
                "question_id": "q2",
                "question": "Q2?",
                "answer": "I don't remember the frameworks, but I used MATLAB and C++.",
                "evaluation": {
                    "score": 0.15,
                    "decision": "advance",
                    "evidence_type": "claimed_unverified",
                    "strengths": [],
                    "weaknesses": [
                        "The candidate claimed experience related to Java but could not "
                        "provide verifiable detail."
                    ],
                    "evidence": [],
                    "follow_up_needed": False,
                    "follow_up_question": None,
                },
            },
        ],
    )


def _weak_plan() -> InterviewPlan:
    return InterviewPlan(
        job_id="job-1",
        role_title="Software Developer",
        occupation_match=OccupationMatch(
            onet_soc_code="15-1252.00", title="Software Developers", score=1.0
        ),
        coverage_targets=[
            CoverageTarget(
                id="q1",
                category=QuestionCategory.TECHNOLOGY,
                target="Python",
                requirement_level=RequirementLevel.REQUIRED,
                source=EvidenceSource.JOBSPEC,
                priority=0,
                grounding="g",
            ),
            CoverageTarget(
                id="q2",
                category=QuestionCategory.TECHNOLOGY,
                target="Java",
                requirement_level=RequirementLevel.REQUIRED,
                source=EvidenceSource.JOBSPEC,
                priority=1,
                grounding="g",
            ),
        ],
    )


async def test_summary_names_specific_gaps_rather_than_a_capability_judgment():
    """Report-review fix: the summary must name which requirements lack sufficient evidence
    (evidence-grounded) rather than asserting a conclusion about the candidate's capability the
    interview evidence doesn't support."""
    service = ReportGenerationService(narrative=ReportNarrativeService(llm=FakeLLMClient()))
    report = await service.generate(
        interview_id="i1", plan=_weak_plan(), state=_weak_completed_state()
    )

    assert "Python" in report.summary
    assert "Java" in report.summary
    assert "capability" not in report.summary.lower()
    assert "concerns about" not in report.summary.lower()

    # The two gaps render as different, accurate labels - not one generic phrase for both.
    by_name = {c.name: c for c in report.competencies}
    assert by_name["Python"].evidence_label == "No evidence"
    assert by_name["Java"].evidence_label == "Unverified claim"


def _plan_with_unassessed_required_target() -> InterviewPlan:
    """Same as `_plan()` (one required target, `q1`, that gets asked) plus a second required
    target, `q2`, that the adaptive interview never reaches - the report must say so honestly
    rather than silently implying full role coverage (see the adaptive-runtime review)."""
    plan = _plan()
    return plan.model_copy(
        update={
            "coverage_targets": [
                *plan.coverage_targets,
                CoverageTarget(
                    id="q2",
                    category=QuestionCategory.TECHNOLOGY,
                    target="PostgreSQL",
                    requirement_level=RequirementLevel.REQUIRED,
                    source=EvidenceSource.JOBSPEC,
                    priority=1,
                    grounding="g",
                ),
            ]
        }
    )


async def test_unassessed_required_targets_are_reported_and_named_honestly():
    """A required target the adaptive interview never reached at all must show up in
    `unassessed_required_targets` and be named in the summary - but never phrased as a failure
    or a gap in the candidate (that would misrepresent "the interview ended early" as "the
    candidate came up short")."""
    service = ReportGenerationService(narrative=ReportNarrativeService(llm=FakeLLMClient()))
    report = await service.generate(
        interview_id="i1",
        plan=_plan_with_unassessed_required_target(),
        state=_completed_state(0.8, "advance"),
    )

    assert report.unassessed_required_targets == ["PostgreSQL"]
    assert "PostgreSQL" in report.summary
    assert "fail" not in report.summary.lower()
    assert "weak" not in report.summary.lower()
    assert "lacks" not in report.summary.lower()


async def test_fully_assessed_plan_has_no_unassessed_targets_or_sentence():
    service = ReportGenerationService(narrative=ReportNarrativeService(llm=FakeLLMClient()))
    report = await service.generate(
        interview_id="i1", plan=_plan(), state=_completed_state(0.8, "advance")
    )

    assert report.unassessed_required_targets == []
    assert "ended before assessing" not in report.summary


async def test_summary_never_overclaims_beyond_the_areas_assessed():
    """Report-review fix: even a strong, well-evidenced result must not be inflated into
    "extensive experience" (asserts a scale the interview can't establish) or a conclusion
    about overall role fit like "reinforces their suitability for the role" (the interview only
    assessed some of the role's requirements, not the whole role)."""
    service = ReportGenerationService(narrative=ReportNarrativeService(llm=FakeLLMClient()))
    report = await service.generate(
        interview_id="i1",
        plan=_plan_with_unassessed_required_target(),
        state=_completed_state(0.95, "advance"),
    )

    assert "extensive" not in report.summary.lower()
    assert "exceptional" not in report.summary.lower()
    assert "reinforces their suitability" not in report.summary.lower()


async def test_report_always_carries_a_fixed_score_basis_note():
    """Item 4 (final backend pass): the score/recommendation must never be misread as fractional
    coverage of the whole role - a fixed, deterministic (never LLM-generated) clarification
    sentence sits next to the score unconditionally, whether or not anything is unassessed."""
    service = ReportGenerationService(narrative=ReportNarrativeService(llm=FakeLLMClient()))
    report = await service.generate(
        interview_id="i1", plan=_plan(), state=_completed_state(0.8, "advance")
    )
    assert report.score_basis_note == (
        "Based on assessed evidence only. Unassessed requirements are not treated as failures."
    )


async def test_completion_reason_reflects_whether_every_required_target_was_reached():
    """Item 6/9.9 (final backend pass): completion_reason is derived, not separately tracked -
    empty unassessed_required_targets means every required target got a turn
    ("sufficient_evidence"); a non-empty list means the interview's total_budget safety cap cut
    it off first ("budget_exhausted") - see InterviewReport.completion_reason's docstring for
    why that's the only other way the current termination architecture can end early."""
    service = ReportGenerationService(narrative=ReportNarrativeService(llm=FakeLLMClient()))

    full = await service.generate(
        interview_id="i1", plan=_plan(), state=_completed_state(0.8, "advance")
    )
    assert full.unassessed_required_targets == []
    assert full.completion_reason == "sufficient_evidence"

    partial = await service.generate(
        interview_id="i1",
        plan=_plan_with_unassessed_required_target(),
        state=_completed_state(0.8, "advance"),
    )
    assert partial.unassessed_required_targets != []
    assert partial.completion_reason == "budget_exhausted"


async def test_narrative_never_conflates_a_weakly_assessed_target_with_a_truly_unassessed_one():
    """Items 9.5/9.6 (final backend pass): a target that WAS asked about but produced weak
    evidence (named via the "did not provide sufficient evidence" gap sentence) must never be
    named in the separate "ended before assessing" sentence reserved for
    unassessed_required_targets, and vice versa - the two sentences are built from disjoint,
    independently-computed sources and must never cross-contaminate."""
    plan = InterviewPlan(
        job_id="job-1",
        role_title="Software Developer",
        occupation_match=OccupationMatch(
            onet_soc_code="15-1252.00", title="Software Developers", score=1.0
        ),
        coverage_targets=[
            CoverageTarget(
                id="python",
                category=QuestionCategory.TECHNOLOGY,
                target="Python",
                requirement_level=RequirementLevel.REQUIRED,
                source=EvidenceSource.JOBSPEC,
                priority=0,
                grounding="g",
            ),
            CoverageTarget(
                id="java",
                category=QuestionCategory.TECHNOLOGY,
                target="Java",
                requirement_level=RequirementLevel.REQUIRED,
                source=EvidenceSource.JOBSPEC,
                priority=1,
                grounding="g",
            ),
            CoverageTarget(
                id="git",
                category=QuestionCategory.TECHNOLOGY,
                target="Git",
                requirement_level=RequirementLevel.REQUIRED,
                source=EvidenceSource.JOBSPEC,
                priority=2,
                grounding="g",
            ),
        ],
    )
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["python", "java"],
        history=[
            {
                "question_id": "python",
                "question": "Q1?",
                "answer": "a detailed, concrete answer about building services in Python",
                "evaluation": {
                    "score": 0.9,
                    "decision": "advance",
                    "evidence_type": "demonstrated",
                    "strengths": ["Built a concrete backend service"],
                    "weaknesses": [],
                    "evidence": ["a detailed, concrete answer"],
                    "follow_up_needed": False,
                    "follow_up_question": None,
                },
            },
            {
                "question_id": "java",
                "question": "Q2?",
                "answer": "I don't remember, but I used MATLAB and C++.",
                "evaluation": {
                    "score": 0.15,
                    "decision": "advance",
                    "evidence_type": "claimed_unverified",
                    "strengths": [],
                    "weaknesses": [
                        "The candidate claimed relevant experience but could not provide "
                        "verifiable detail."
                    ],
                    "evidence": [],
                    "follow_up_needed": False,
                    "follow_up_question": None,
                },
            },
        ],
    )
    service = ReportGenerationService(narrative=ReportNarrativeService(llm=FakeLLMClient()))
    report = await service.generate(interview_id="i1", plan=plan, state=state)

    # Java was assessed (weakly) - it must never appear in unassessed_required_targets, and
    # only Git (never reached at all) does.
    assert report.unassessed_required_targets == ["Git"]

    assert "did not provide sufficient evidence that the candidate meets" in report.summary
    assert "ended before assessing" in report.summary

    gap_clause = report.summary.split("did not provide sufficient evidence", 1)[1].split(".")[0]
    unassessed_clause = report.summary.split("ended before assessing", 1)[1].split(".")[0]
    assert "Java" in gap_clause
    assert "Git" not in gap_clause
    assert "Git" in unassessed_clause
    assert "Java" not in unassessed_clause


async def test_generate_deterministic_fields_stable_across_repeated_calls():
    service = ReportGenerationService(narrative=ReportNarrativeService(llm=FakeLLMClient()))
    state = _completed_state(0.8, "advance")

    first = await service.generate(interview_id="i1", plan=_plan(), state=state)
    second = await service.generate(interview_id="i1", plan=_plan(), state=state)

    assert first.overall_score == second.overall_score
    assert first.recommendation == second.recommendation
    assert first.competencies == second.competencies
    assert first.question_evaluations == second.question_evaluations
