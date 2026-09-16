"""Interview-report use case: completed interview -> evidence-based InterviewReport.

Deterministic aggregation (:mod:`app.services.report_scoring`) and LLM narrative synthesis
(:mod:`app.services.report_narrative`) are deliberately kept separate: this service is the
only place that combines them, and it never lets the narrative step touch the score or
recommendation. If narrative synthesis fails or produces nothing usable, this falls back to a
deterministic, template-based narrative instead of failing the whole report - an LLM outage
must not take report generation down with it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.exceptions import LLMError
from app.domain.interview import InterviewState
from app.domain.interview_plan import InterviewPlan
from app.domain.report import (
    CompetencyAssessment,
    EvidenceStrength,
    InterviewReport,
    Recommendation,
)
from app.services.report_narrative import ReportNarrativeService
from app.services.report_scoring import (
    build_areas_to_explore,
    build_competency_assessments,
    build_question_evaluations,
    build_strengths,
    compute_overall_score,
    derive_recommendation,
    evidence_strength_for_score,
)

logger = logging.getLogger(__name__)

_FALLBACK_LIST_LIMIT = 5

#: Plain-language read of the candidate's overall performance, keyed by the same qualitative
#: band used per-competency (see ``EvidenceStrength``) - describes what the interview showed,
#: not how the score was computed. Used only by the deterministic fallback narrative; the real
#: narrative prompt is instructed to write its own equivalent phrasing.
_SUMMARY_PHRASES: dict[EvidenceStrength, str] = {
    EvidenceStrength.STRONG: (
        "demonstrated strong, well-evidenced performance across the areas assessed"
    ),
    EvidenceStrength.MODERATE: (
        "demonstrated solid performance, with some areas worth exploring further"
    ),
    EvidenceStrength.LIMITED: "showed limited evidence across the areas assessed",
    EvidenceStrength.INSUFFICIENT: (
        "did not provide enough concrete evidence across the areas assessed to draw firm "
        "conclusions"
    ),
    # overall_evidence_strength is derived from overall_score, a float that defaults to 0.0
    # rather than None (see compute_overall_score) - so it can never actually be NOT_ASSESSED
    # in practice. Included only so this mapping is total over the enum.
    EvidenceStrength.NOT_ASSESSED: (
        "did not provide enough concrete evidence across the areas assessed to draw firm "
        "conclusions"
    ),
}


def _deterministic_narrative(
    *,
    overall_score: float,
    overall_evidence_strength: EvidenceStrength,
    recommendation: Recommendation,
    competencies: list[CompetencyAssessment],
) -> tuple[str, list[str], list[str]]:
    """Template-based summary/strengths/weaknesses built only from already-computed data.

    Used both as the report's narrative when no LLM is configured for it to add value beyond,
    and as the fallback when LLM synthesis fails - always available, always evidence-based.
    Deliberately phrased around the *candidate's* performance, never the scoring mechanism
    (no "deterministic", no raw percentages) - see the Milestone report-quality review.
    """
    summary = (
        f"Across the interview, the candidate {_SUMMARY_PHRASES[overall_evidence_strength]}. "
        f"This supports a recommendation of {recommendation.value.replace('_', ' ')}."
    )
    strengths = build_strengths(competencies, limit=_FALLBACK_LIST_LIMIT)
    weaknesses = build_areas_to_explore(competencies, limit=_FALLBACK_LIST_LIMIT)
    return summary, strengths, weaknesses


@dataclass
class ReportGenerationService:
    narrative: ReportNarrativeService

    async def generate(
        self, *, interview_id: str, plan: InterviewPlan, state: InterviewState
    ) -> InterviewReport:
        """Build the evidence-based report for a completed interview.

        Pure with respect to LLM behaviour: ``overall_score``, ``recommendation``,
        ``competencies``, and ``question_evaluations`` are computed before the narrative call
        and are never modified by it, whether it succeeds or fails.
        """
        question_evaluations = build_question_evaluations(plan, state)
        competencies = build_competency_assessments(question_evaluations)
        overall_score = compute_overall_score(competencies)
        overall_evidence_strength = evidence_strength_for_score(overall_score)
        recommendation = derive_recommendation(overall_score)

        summary, strengths, weaknesses = _deterministic_narrative(
            overall_score=overall_score,
            overall_evidence_strength=overall_evidence_strength,
            recommendation=recommendation,
            competencies=competencies,
        )

        try:
            narrative = await self.narrative.synthesize(
                overall_score=overall_score,
                recommendation=recommendation.value,
                competencies=competencies,
            )
        except LLMError:
            logger.warning(
                "Report narrative synthesis failed for interview %s; using the deterministic "
                "fallback narrative instead.",
                interview_id,
                exc_info=True,
            )
        else:
            # Only the summary prose is ever taken from the narrative step now - strengths/
            # areas-to-explore stay exactly the deterministic, name-prefixed, ranked-and-capped
            # lists from `build_strengths`/`build_areas_to_explore` (see the report-quality
            # review: letting an LLM re-list them reintroduced unprefixed, unranked, sometimes
            # duplicated-sounding items with no guarantee of improving on the deterministic
            # version - the fake client, for instance, only ever echoes them back flattened).
            if narrative.summary.strip():
                summary = narrative.summary

        return InterviewReport(
            interview_id=interview_id,
            job_id=state.job_id,
            overall_score=overall_score,
            recommendation=recommendation,
            summary=summary,
            strengths=strengths,
            weaknesses=weaknesses,
            competencies=competencies,
            question_evaluations=question_evaluations,
        )
