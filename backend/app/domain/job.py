"""Domain models describing a job and its structured specification.

`JobSpec` is the structured-output target of the JD-analysis step.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Seniority(StrEnum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"
    UNKNOWN = "unknown"


class Skill(BaseModel):
    """A concrete technology, tool, language, or methodology named in the JD."""

    name: str
    required: bool = Field(
        default=True,
        description="True for must-have skills, False for preferred / nice-to-have.",
    )


class Competency(BaseModel):
    """A behavioural or role competency to assess in the interview."""

    name: str
    description: str | None = None


class JobSpec(BaseModel):
    """Structured representation of a job description.

    This is the sole authoritative source of what a candidate is evaluated on - see
    ``app.services.interview_planner``'s module docstring for the full principle. ``skills``,
    ``competencies``, and ``responsibilities`` together are the complete set of interview
    requirements; nothing outside this model may silently add another one.
    """

    role_title: str
    seniority: Seniority = Seniority.UNKNOWN
    skills: list[Skill] = Field(default_factory=list)
    competencies: list[Competency] = Field(default_factory=list)
    responsibilities: list[str] = Field(
        default_factory=list,
        description="Day-to-day duties/tasks stated in the JD, in JD order.",
    )
    summary: str | None = None
