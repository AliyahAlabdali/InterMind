"""Answer-evaluation use case: interview question + candidate answer -> AnswerEvaluation.

Mirrors :class:`app.services.jd_analysis.JDAnalysisService` and
:class:`app.services.question_generation.QuestionGenerationService`: the LLM only produces a
validated :class:`~app.domain.evaluation.AnswerEvaluation` through the same
:class:`~app.llm.ports.LLMClient` boundary. Deciding what to *do* with that evaluation (advance,
follow up, finish) happens in :mod:`app.agents.interview_graph` - this service only grounds and
scores one answer.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.evaluation import AnswerEvaluation
from app.llm.ports import LLMClient
from app.llm.prompts import load_prompt

PROMPT_NAME = "answer_evaluation"
PROMPT_VERSION = "v1"


@dataclass
class AnswerEvaluationService:
    llm: LLMClient

    async def evaluate(
        self,
        *,
        question_text: str,
        category: str,
        target: str,
        answer: str,
        grounding: str | None = None,
        other_targets: list[tuple[str, str]] = (),
    ) -> AnswerEvaluation:
        """Return a grounded, structured evaluation of ``answer``.

        ``other_targets`` (optional, ``(category, target_name)`` pairs) lists the interview's
        other not-yet-assessed coverage targets - see
        :mod:`app.services.cross_target_evidence`. When given, the model may also report
        ``cross_target_evidence`` for any of them the answer incidentally provides evidence
        about (e.g. a Python question where the candidate also mentions Java experience) -
        never as a target of *this* evaluation's own ``score``/``decision``, only as a
        separate, clearly-scoped signal the interview graph may use to resolve that other
        target without asking about it directly.

        Raises:
            app.core.exceptions.LLMError: the request failed or the output was unusable.
        """
        lines = [
            f"QUESTION: {question_text}",
            f"CATEGORY: {category}",
            f"TARGET: {target}",
        ]
        if grounding:
            lines.append(f"GROUNDING: {grounding}")
        if other_targets:
            lines.append("OTHER_TARGETS:")
            lines.extend(
                f"- {other_category}: {other_name}" for other_category, other_name in other_targets
            )
        lines.append(f"ANSWER: {answer.strip()}")

        prompt = load_prompt(PROMPT_NAME, PROMPT_VERSION)
        return await self.llm.generate_structured(
            prompt=prompt,
            input_text="\n".join(lines),
            schema=AnswerEvaluation,
        )
