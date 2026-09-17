"""OpenAI implementation of :class:`app.llm.ports.LLMClient` using structured outputs."""

from __future__ import annotations

import logging
import time
from typing import TypeVar

from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from app.core.exceptions import LLMError, LLMOutputInvalid
from app.observability.trace import TraceRecorder

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class OpenAIStructuredClient:
    """Calls the OpenAI chat completions parse API and returns a validated model."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        trace: TraceRecorder | None = None,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._trace = trace or TraceRecorder()

    async def generate_structured(
        self,
        *,
        prompt: str,
        input_text: str,
        schema: type[T],
    ) -> T:
        self._trace.record(
            operation="generate_structured",
            provider="openai",
            model=self._model,
            schema=schema.__name__,
            input_chars=len(input_text),
        )
        # Latency instrumentation (adaptive-runtime review, item 6): `schema` distinguishes an
        # answer-evaluation call from a question-generation call, so this one measurement point
        # is enough to see both LLM calls' individual cost - no separate timing plumbing needed
        # through app.services.answer_evaluation/question_generation. Recorded via the same
        # TraceRecorder already threaded through this client (see the module docstring), not a
        # new logging mechanism.
        started_at = time.perf_counter()
        try:
            completion = await self._client.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": input_text},
                ],
                response_format=schema,
            )
        except OpenAIError as exc:
            self._trace.record(
                operation="generate_structured_failed",
                provider="openai",
                schema=schema.__name__,
                duration_seconds=round(time.perf_counter() - started_at, 3),
            )
            logger.exception("OpenAI request failed")
            raise LLMError(f"OpenAI request failed: {exc}") from exc
        except Exception as exc:
            # Defensive: never let a raw SDK/runtime error leak past this boundary.
            self._trace.record(
                operation="generate_structured_failed",
                provider="openai",
                schema=schema.__name__,
                duration_seconds=round(time.perf_counter() - started_at, 3),
            )
            logger.exception("Unexpected error calling OpenAI")
            raise LLMError(f"Unexpected error calling OpenAI: {exc}") from exc

        duration_seconds = round(time.perf_counter() - started_at, 3)
        self._trace.record(
            operation="generate_structured_completed",
            provider="openai",
            model=self._model,
            schema=schema.__name__,
            duration_seconds=duration_seconds,
        )

        if not completion.choices:
            raise LLMOutputInvalid("OpenAI returned no choices")

        message = completion.choices[0].message
        if getattr(message, "refusal", None):
            raise LLMOutputInvalid(f"OpenAI refused the request: {message.refusal}")
        if message.parsed is None:
            raise LLMOutputInvalid("OpenAI returned no parsed content")

        try:
            return schema.model_validate(message.parsed)
        except ValidationError as exc:
            raise LLMOutputInvalid(str(exc)) from exc
