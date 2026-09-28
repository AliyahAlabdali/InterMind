"""LLM-based narrative synthesis for interview reports - summary/strengths/weaknesses ONLY.

Mirrors :class:`app.services.answer_evaluation.AnswerEvaluationService`: a single
:class:`~app.llm.ports.LLMClient`-backed call behind a versioned prompt, returning a
validated Pydantic model. This service never sees anything but the already-computed,
deterministic competency assessments (:mod:`app.services.report_scoring`) rendered as plain
text - it has no field through which to set a score, and its output cannot change the
report's ``overall_score`` or ``recommendation`` (see :mod:`app.services.report_generation`).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.report import CompetencyAssessment, ReportNarrative
from app.llm.ports import LLMClient
from app.llm.prompts import load_prompt

PROMPT_NAME = "interview_report"
PROMPT_VERSION = "v1"


@dataclass
class ReportNarrativeService:
    llm: LLMClient

    async def synthesize(
        self,
        *,
        overall_score: float,
        recommendation: str,
        competencies: list[CompetencyAssessment],
        unassessed_required_targets: list[str] = (),
    ) -> ReportNarrative:
        """Return a concise narrative synthesis grounded only in ``competencies``.

        ``unassessed_required_targets`` (see
        ``app.services.report_scoring.build_unassessed_required_targets``) lists required
        targets the adaptive interview never reached at all - distinct from a target that was
        asked about but scored poorly (already reflected in ``competencies``). Passed through
        so the narrative can name them honestly rather than silently implying every requirement
        was covered - never as evidence of any kind about the candidate.

        Raises:
            app.core.exceptions.LLMError: the request failed or the output was unusable.
        """
        lines = [
            f"OVERALL_SCORE: {overall_score:.2f}",
            f"RECOMMENDATION: {recommendation}",
            "UNASSESSED_REQUIRED_TARGETS: "
            + (", ".join(unassessed_required_targets) if unassessed_required_targets else "(none)"),
        ]
        for c in competencies:
            lines.append("---")
            lines.append(f"COMPETENCY: {c.name}")
            lines.append(f"CATEGORY: {c.category.value}")
            lines.append(f"EVIDENCE_STRENGTH: {c.evidence_strength.value}")
            lines.append(f"EVIDENCE_TYPE: {c.evidence_type.value if c.evidence_type else 'none'}")
            lines.append(f"STRENGTHS: {'; '.join(c.strengths) or '(none)'}")
            lines.append(f"WEAKNESSES: {'; '.join(c.weaknesses) or '(none)'}")
            lines.append(f"EVIDENCE: {'; '.join(c.evidence) or '(none)'}")

        prompt = load_prompt(PROMPT_NAME, PROMPT_VERSION)
        return await self.llm.generate_structured(
            prompt=prompt,
            input_text="\n".join(lines),
            schema=ReportNarrative,
        )
