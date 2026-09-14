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
from app.domain.report import CompetencyAssessment, InterviewReport, Recommendation
from app.services.report_narrative import ReportNarrativeService
from app.services.report_scoring import (
    build_competency_assessments,
    build_question_evaluations,
    compute_overall_score,
    derive_recommendation,
    flatten_unique,
)

logger = logging.getLogger(__name__)

_FALLBACK_LIST_LIMIT = 5


def _deterministic_narrative(
    *,
    overall_score: float,
    recommendation: Recommendation,
    competencies: list[CompetencyAssessment],
) -> tuple[str, list[str], list[str]]:
    """Template-based summary/strengths/weaknesses built only from already-computed data.

    Used both as the report's narrative when no LLM is configured for it to add value beyond,
    and as the fallback when LLM synthesis fails - always available, always evidence-based.
    """
    plural = "y" if len(competencies) == 1 else "ies"
    summary = (
        f"Evaluated {len(competencies)} competenc{plural} with an overall score of "
        f"{overall_score:.2f}, recommending {recommendation.value}."
    )
    strengths = flatten_unique(c.strengths for c in competencies)[:_FALLBACK_LIST_LIMIT]
    weaknesses = flatten_unique(c.weaknesses for c in competencies)[:_FALLBACK_LIST_LIMIT]
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
        recommendation = derive_recommendation(overall_score)

        summary, strengths, weaknesses = _deterministic_narrative(
            overall_score=overall_score, recommendation=recommendation, competencies=competencies
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
            if narrative.summary.strip():
                summary = narrative.summary
            if narrative.strengths:
                strengths = narrative.strengths
            if narrative.weaknesses:
                weaknesses = narrative.weaknesses

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
