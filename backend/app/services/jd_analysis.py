"""JD analysis use case: raw job-description text -> structured :class:`JobSpec`."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.job import JobSpec
from app.llm.ports import LLMClient
from app.llm.prompts import load_prompt

PROMPT_NAME = "jd_analysis"
PROMPT_VERSION = "v1"


@dataclass
class JDAnalysisService:
    """Turns a job description into a :class:`JobSpec` using the configured LLM client.

    The interface is a single coroutine so a later milestone can wrap it as one node in a
    stateful graph without changing callers.
    """

    llm: LLMClient

    async def analyze(self, job_description: str) -> JobSpec:
        text = job_description.strip()
        if not text:
            raise ValueError("job_description must not be empty")
        prompt = load_prompt(PROMPT_NAME, PROMPT_VERSION)
        return await self.llm.generate_structured(
            prompt=prompt,
            input_text=text,
            schema=JobSpec,
        )
