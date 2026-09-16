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
    """One competency selected for the interview plan, with its provenance.

    Always sourced from :attr:`~app.domain.job.JobSpec.competencies` - ``source`` is
    ``jobspec`` normally, or ``both`` when the matched O*NET occupation happens to rate the
    same competency (in which case ``onet_importance``/``onet_level`` are also populated).
    O*NET never contributes a *new* competency the JD didn't already name; see the module
    docstring in ``app.services.interview_planner``.
    """

    name: str
    source: EvidenceSource
    onet_importance: float | None = None
    onet_level: float | None = None


class SelectedTechnology(BaseModel):
    """One technology selected for the interview plan, with its provenance.

    Always sourced from :attr:`~app.domain.job.JobSpec.skills` - ``source`` is ``jobspec``
    normally, or ``both`` when the matched O*NET occupation also lists the same technology (in
    which case ``hot``/``in_demand`` are also populated). O*NET never contributes a *new*
    technology the JD didn't already name; see the module docstring in
    ``app.services.interview_planner``. ``required`` mirrors the JobSpec skill's own
    required/preferred flag (see :class:`~app.domain.job.Skill`).
    """

    name: str
    source: EvidenceSource
    required: bool | None = None
    hot: bool = False
    in_demand: bool = False


class SelectedTask(BaseModel):
    """One responsibility/task selected for the interview plan, with its provenance.

    Sourced from :attr:`~app.domain.job.JobSpec.responsibilities` (the JD's own stated
    duties) - ``source`` is ``jobspec`` in the overwhelming majority of cases. ``both`` is
    possible but rare: it only fires when a JD responsibility happens to normalize to the
    exact same text as one of the matched occupation's O*NET core tasks. O*NET never supplies
    a *new* task on its own; see the module docstring in ``app.services.interview_planner``.
    """

    task: str
    source: EvidenceSource


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
    onet_grounding_used: bool = Field(
        default=True,
        description=(
            "Whether the matched O*NET occupation actually contributed usable context to "
            "question generation (see InterviewPlannerService._build_onet_context). This has "
            "never meant O*NET items were added to competencies/technologies/tasks below - "
            "those are always JobSpec-only (see EvidenceSource) - only whether O*NET was used "
            "to help *phrase* questions. False means the match was too weak/ambiguous, or "
            "simply had nothing relevant to offer this JobSpec; occupation_match/"
            "alternate_matches are still returned for transparency either way."
        ),
    )
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
