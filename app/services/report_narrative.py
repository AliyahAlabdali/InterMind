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
    ) -> ReportNarrative:
        """Return a concise narrative synthesis grounded only in ``competencies``.

        Raises:
            app.core.exceptions.LLMError: the request failed or the output was unusable.
        """
        lines = [
            f"OVERALL_SCORE: {overall_score:.2f}",
            f"RECOMMENDATION: {recommendation}",
        ]
        for c in competencies:
            lines.append("---")
            lines.append(f"COMPETENCY: {c.name}")
            lines.append(f"CATEGORY: {c.category.value}")
            lines.append(f"SCORE: {c.score:.2f}" if c.score is not None else "SCORE: (no evidence)")
            lines.append(f"STRENGTHS: {'; '.join(c.strengths) or '(none)'}")
            lines.append(f"WEAKNESSES: {'; '.join(c.weaknesses) or '(none)'}")
            lines.append(f"EVIDENCE: {'; '.join(c.evidence) or '(none)'}")

        prompt = load_prompt(PROMPT_NAME, PROMPT_VERSION)
        return await self.llm.generate_structured(
            prompt=prompt,
            input_text="\n".join(lines),
            schema=ReportNarrative,
        )
