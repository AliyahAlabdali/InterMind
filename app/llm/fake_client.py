"""Deterministic, offline implementation of :class:`app.llm.ports.LLMClient`.

Used by the test suite and for local development without an API key
(``LLM_PROVIDER=fake``).
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.core.exceptions import LLMOutputInvalid
from app.domain.interview_plan import GeneratedQuestion, GeneratedQuestionSet
from app.domain.job import Competency, JobSpec, Seniority, Skill

T = TypeVar("T", bound=BaseModel)

_QUESTION_TEMPLATES = {
    "competency": "As a {role}, tell me about a time you demonstrated {target}.",
    "technology": "As a {role}, walk me through a project where you used {target} to solve a "
    "real problem.",
    "task": "As a {role}, how would you approach the following responsibility: {target}",
}
_DEFAULT_ROLE = "professional"


def _fake_generate_questions(input_text: str) -> GeneratedQuestionSet:
    """Deterministically template one question per ``CATEGORY: target`` line.

    Expects the format produced by :class:`app.services.question_generation.
    QuestionGenerationService`: a ``ROLE:`` line followed by one ``COMPETENCY:``/
    ``TECHNOLOGY:``/``TASK:`` line per target. The role title is folded into every question's
    text (so two different roles deterministically produce different question text for the
    same target), not just parsed and discarded. Unrecognised lines are skipped rather than
    raising, so this stays robust to minor prompt/format drift.
    """
    role = _DEFAULT_ROLE
    questions = []
    for line in input_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith("ROLE:"):
            _, _, role_value = line.partition(":")
            role_value = role_value.strip()
            if role_value:
                role = role_value
            continue
        category, _, name = line.partition(":")
        category = category.strip().lower()
        name = name.strip()
        template = _QUESTION_TEMPLATES.get(category)
        if not name or template is None:
            continue
        text = template.format(role=role, target=name)
        questions.append(GeneratedQuestion(category=category, target=name, text=text))
    return GeneratedQuestionSet(questions=questions)


class FakeLLMClient:
    """Returns a fixed response, either a caller-supplied one or a canned default."""

    def __init__(self, response: BaseModel | None = None) -> None:
        self._response = response

    async def generate_structured(
        self,
        *,
        prompt: str,
        input_text: str,
        schema: type[T],
    ) -> T:
        if self._response is not None:
            if not isinstance(self._response, schema):
                raise LLMOutputInvalid(
                    f"Configured fake response is {type(self._response).__name__}, "
                    f"expected {schema.__name__}"
                )
            return self._response

        if schema is JobSpec:
            first_line = next(
                (line.strip() for line in input_text.splitlines() if line.strip()),
                "Unknown Role",
            )
            return schema.model_validate(
                JobSpec(
                    role_title=first_line[:120],
                    seniority=Seniority.MID,
                    skills=[
                        Skill(name="Python", required=True),
                        Skill(name="FastAPI", required=False),
                    ],
                    competencies=[
                        Competency(
                            name="Problem solving",
                            description="Breaks ambiguous problems into tractable steps.",
                        )
                    ],
                    summary="Deterministic fake analysis for local development and tests.",
                )
            )

        if schema is GeneratedQuestionSet:
            return _fake_generate_questions(input_text)

        raise LLMOutputInvalid(
            f"FakeLLMClient has no canned response for schema {schema.__name__}"
        )
