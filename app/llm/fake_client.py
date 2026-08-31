"""Deterministic, offline implementation of :class:`app.llm.ports.LLMClient`.

Used by the test suite and for local development without an API key
(``LLM_PROVIDER=fake``).
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.core.exceptions import LLMOutputInvalid
from app.domain.job import Competency, JobSpec, Seniority, Skill

T = TypeVar("T", bound=BaseModel)


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

        raise LLMOutputInvalid(
            f"FakeLLMClient has no canned response for schema {schema.__name__}"
        )
