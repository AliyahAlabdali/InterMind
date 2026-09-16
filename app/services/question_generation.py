"""Question-phrasing use case: role title + targets -> grounded question text.

Mirrors :class:`app.services.jd_analysis.JDAnalysisService`: the LLM only supplies question
*phrasing*, structured and validated through the same :class:`~app.llm.ports.LLMClient`
boundary. Deciding *what* to ask about (which competencies/technologies/tasks) happens
upstream in :class:`app.services.interview_planner.InterviewPlannerService` - this service
takes that selection as given.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import QuestionGenerationError
from app.domain.interview_plan import GeneratedQuestion, GeneratedQuestionSet
from app.llm.ports import LLMClient
from app.llm.prompts import load_prompt
from app.services.text_normalize import normalize_name

PROMPT_NAME = "interview_questions"
PROMPT_VERSION = "v1"


@dataclass
class QuestionGenerationService:
    llm: LLMClient

    async def generate(
        self, *, role_title: str, targets: list[tuple[str, str]], onet_context: str = ""
    ) -> GeneratedQuestionSet:
        """Return one phrased question per ``(category, target_name)`` pair in ``targets``.

        ``category`` must be one of ``"competency"``, ``"technology"``, ``"task"``.

        ``onet_context``, when non-empty, is supplementary occupational context (matched
        occupation title plus a few relevance-filtered technologies/tasks - see
        ``InterviewPlannerService._build_onet_context``) appended for the LLM to draw on when
        *phrasing* questions. It is never itself a target: it must not change which or how
        many questions are generated, and a real LLM must not invent a new requirement from it
        - see ``interview_questions_v1.md``.

        Raises:
            app.core.exceptions.QuestionGenerationError: the provider's response - whether
                from the fake client or a real LLM - does not contain exactly one question
                per requested target, in the requested order. Never silently dropped.
        """
        if not targets:
            return GeneratedQuestionSet(questions=[])

        lines = [f"ROLE: {role_title}"]
        lines += [f"{category.upper()}: {name}" for category, name in targets]
        if onet_context:
            lines += ["", "ONET_CONTEXT:", onet_context]
        prompt = load_prompt(PROMPT_NAME, PROMPT_VERSION)
        result = await self.llm.generate_structured(
            prompt=prompt,
            input_text="\n".join(lines),
            schema=GeneratedQuestionSet,
        )
        _validate_generated(targets, result.questions)
        return result


def _key(category: str, target: str) -> tuple[str, str]:
    return category.strip().lower(), normalize_name(target)


def _validate_generated(
    targets: list[tuple[str, str]], questions: list[GeneratedQuestion]
) -> None:
    """Check ``questions`` is exactly one response per requested target, in order.

    A mis-categorised response (right target text, wrong category, or vice versa) surfaces
    as that target simultaneously appearing "unexpected" (under the wrong key) and "missing"
    (under the right key) - no separate category check is needed to catch it.
    """
    requested = [_key(category, target) for category, target in targets]
    returned = [_key(q.category, q.target) for q in questions]

    seen: set[tuple[str, str]] = set()
    duplicates: set[tuple[str, str]] = set()
    for key in returned:
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    if duplicates:
        raise QuestionGenerationError(
            f"Generated questions contain duplicate target(s): {sorted(duplicates)}"
        )

    requested_set = set(requested)
    unexpected = [key for key in returned if key not in requested_set]
    if unexpected:
        raise QuestionGenerationError(
            f"Generated questions contain unrequested target(s): {unexpected}"
        )

    returned_set = set(returned)
    missing = [key for key in requested if key not in returned_set]
    if missing:
        raise QuestionGenerationError(
            f"Generated questions are missing requested target(s): {missing}"
        )

    # No duplicates, nothing unexpected, nothing missing: `returned` is some ordering of
    # exactly `requested`. It must match order-for-order, not just as a set.
    if returned != requested:
        raise QuestionGenerationError(
            "Generated questions are not in the requested target order: "
            f"expected {requested}, got {returned}"
        )
