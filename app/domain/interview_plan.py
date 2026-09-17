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

from app.domain.job import Seniority
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


class RequirementLevel(StrEnum):
    """Whether the job description treats a target as must-have or nice-to-have.

    Technologies inherit this directly from :attr:`~app.domain.job.Skill.required`.
    Competencies and tasks have no such distinction in :class:`~app.domain.job.JobSpec` (a JD
    names a competency/responsibility because it matters, full stop) - see
    ``InterviewPlannerService`` for where each category's level is actually decided.
    """

    REQUIRED = "required"
    PREFERRED = "preferred"


class AssessmentStatus(StrEnum):
    """Whether a coverage target has been assessed yet.

    A :class:`CoverageTarget` on an :class:`InterviewPlan` is always ``NOT_ASSESSED`` - the plan
    is a JD-level artifact built before any candidate answers anything, so it has no notion of
    "this candidate's" progress. Live, per-candidate assessment status lives in the interview
    session's own history (see ``app.agents.interview_graph``) and the generated report (see
    ``app.domain.report``), not here - this field exists so ``CoverageTarget`` is
    self-describing about that distinction rather than silently omitting a status concept
    entirely.
    """

    NOT_ASSESSED = "not_assessed"


class CoverageTarget(BaseModel):
    """One thing the interview should assess - WHAT to cover, never pre-written question text.

    Replaces the old fixed, pre-generated ``InterviewQuestion`` list as the plan's main
    interview-facing artifact: the actual question text for a target is generated at runtime,
    once that target is actually selected during a live interview (see
    ``app.agents.interview_graph`` and ``app.services.target_selection``), using the target
    plus everything asked/answered so far - never predetermined here. This is the architectural
    fix for the reported "fixed 7-question script" issue: the plan defines *what* to assess,
    the interview graph decides *what to ask* and *when*, and the number of questions actually
    asked is an outcome of that adaptive process, not a property of the plan.

    ``id`` is a stable, deterministic identity for this target (see
    ``app.services.target_identity.target_question_id``) - the interview graph uses it verbatim
    as the id of whatever question ends up being generated for this target, exactly as it used
    to trust a pre-generated ``InterviewQuestion.id``.
    """

    id: str
    target: str
    category: QuestionCategory
    requirement_level: RequirementLevel
    source: EvidenceSource
    priority: int = Field(
        description=(
            "Lower sorts first within the same category. Required targets are given a lower "
            "priority value than preferred ones, and JD order is preserved within each - see "
            "InterviewPlannerService._build_coverage_targets."
        )
    )
    grounding: str = Field(description="Human-readable evidence reference for this target.")
    assessment_status: AssessmentStatus = AssessmentStatus.NOT_ASSESSED


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
    """One interview question actually generated at runtime for a specific target.

    No longer a plan-level artifact (see :class:`CoverageTarget`) - this shape is used by the
    runtime question-generation path (``app.services.question_generation``,
    ``app.agents.interview_graph``) to represent a single generated question, and by the
    ``FakeLLMClient``/tests that need to construct one.
    """

    id: str
    category: QuestionCategory
    text: str
    target: str = Field(description="Competency/technology/task name this question targets.")
    grounding: str = Field(description="Human-readable evidence reference for this question.")


class InterviewPlan(BaseModel):
    """A structured, role-specific interview plan generated from a JobSpec.

    ``coverage_targets`` is what the adaptive interview actually works from (see
    :class:`CoverageTarget`) - it is not a fixed question script, and its length is not the
    number of questions a candidate will be asked (that is decided at interview time by
    ``app.services.target_selection``). ``competencies``/``technologies``/``tasks`` remain the
    detailed, per-category provenance breakdown they always were (unchanged) - ``coverage_
    targets`` is a flat, prioritized, id-bearing view built from exactly those three lists, for
    the interview graph and for a recruiter-facing "what will this interview cover" summary.
    """

    job_id: str
    role_title: str = Field(
        description=(
            "Copied from the JobSpec at plan-build time so the interview graph can phrase "
            "runtime-generated questions without needing to re-fetch the JobSpec."
        )
    )
    seniority: Seniority = Field(
        default=Seniority.UNKNOWN,
        description="Copied from the JobSpec, for the same reason as role_title above.",
    )
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
    onet_context: str = Field(
        default="",
        description=(
            "The same relevance-filtered O*NET context block described by onet_grounding_used, "
            "persisted here (rather than only used transiently at plan-build time) so the "
            "interview graph can pass it to each runtime question-generation call."
        ),
    )
    competencies: list[CompetencyCoverage] = Field(default_factory=list)
    technologies: list[SelectedTechnology] = Field(default_factory=list)
    tasks: list[SelectedTask] = Field(default_factory=list)
    coverage_targets: list[CoverageTarget] = Field(default_factory=list)


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
