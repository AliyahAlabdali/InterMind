"""Domain models for a structured, role-specific interview plan.

An :class:`InterviewPlan` is built once per job from a :class:`~app.domain.job.JobSpec` plus
its matched O*NET occupation signal (see :mod:`app.services.interview_planner`). It is
distinct from :class:`~app.domain.interview.InterviewState`, which will track progress
*through* a plan once the stateful interview loop exists (Milestone 4) - this module only
describes *what* to ask, never *where the candidate is* in answering it.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.domain.occupation import OccupationMatch


class QuestionCategory(StrEnum):
    COMPETENCY = "competency"
    TECHNOLOGY = "technology"
    TASK = "task"


class EvidenceSource(StrEnum):
    """Where a selected signal came from."""

    JOBSPEC = "jobspec"
    ONET = "onet"
    BOTH = "both"


class CompetencyCoverage(BaseModel):
    """One competency selected for the interview plan, with its provenance."""

    name: str
    source: EvidenceSource
    onet_importance: float | None = None
    onet_level: float | None = None


class SelectedTechnology(BaseModel):
    """One technology selected for the interview plan, with its provenance."""

    name: str
    source: EvidenceSource
    hot: bool = False
    in_demand: bool = False


class SelectedTask(BaseModel):
    """One O*NET core task selected for the interview plan.

    ``source`` is always :attr:`EvidenceSource.ONET`: JobSpec has no task-level field to
    supply an alternate provenance (see :class:`~app.domain.job.JobSpec`), so there is no
    ``jobspec``/``both`` case to represent here. The field exists for schema consistency with
    :class:`CompetencyCoverage` and :class:`SelectedTechnology`, not because O*NET or the
    JobSpec support any other task provenance - nothing is invented.
    """

    task: str
    source: EvidenceSource = EvidenceSource.ONET


class InterviewQuestion(BaseModel):
    """One interview question, grounded in a specific selected signal."""

    id: str
    category: QuestionCategory
    text: str
    target: str = Field(description="Competency/technology/task name this question targets.")
    grounding: str = Field(description="Human-readable evidence reference for this question.")


class InterviewPlan(BaseModel):
    """A structured, role-specific interview plan generated from a JobSpec."""

    job_id: str
    occupation_match: OccupationMatch
    alternate_matches: list[OccupationMatch] = Field(default_factory=list)
    competencies: list[CompetencyCoverage] = Field(default_factory=list)
    technologies: list[SelectedTechnology] = Field(default_factory=list)
    tasks: list[SelectedTask] = Field(default_factory=list)
    questions: list[InterviewQuestion] = Field(default_factory=list)


class GeneratedQuestion(BaseModel):
    """Raw LLM output for one question: phrasing only, no id/grounding yet."""

    category: str
    target: str
    text: str


class GeneratedQuestionSet(BaseModel):
    """Structured-output schema for the question-phrasing LLM call.

    Kept in the domain layer (not ``app.services``) so :mod:`app.llm.fake_client` can
    synthesize a deterministic response for it without the LLM layer depending on services.
    """

    questions: list[GeneratedQuestion] = Field(default_factory=list)
