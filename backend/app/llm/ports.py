"""The LLM boundary. Services depend on this Protocol, never on a concrete SDK."""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    """Produces a validated Pydantic model from an instruction prompt and input text."""

    async def generate_structured(
        self,
        *,
        prompt: str,
        input_text: str,
        schema: type[T],
    ) -> T:
        """Return an instance of ``schema`` derived from ``prompt`` + ``input_text``.

        Raises:
            app.core.exceptions.LLMError: the request failed or the output was unusable.
        """
        ...
