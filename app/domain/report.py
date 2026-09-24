"""Domain models for the evidence-based interview report (Milestone 5).

Built entirely from data already collected during the interview: the InterviewPlan's
questions/targets/grounding and the completed InterviewState's history of (question, answer,
AnswerEvaluation) turns - see :mod:`app.services.report_scoring`. Nothing here is invented:
every :class:`CompetencyAssessment` and :class:`QuestionEvaluationSummary` traces back to a
specific evaluated answer, and ``overall_score``/``recommendation`` are computed
deterministically (:mod:`app.services.report_scoring`) - never by the LLM.
:class:`ReportNarrative` is the one LLM-produced shape here, and it deliberately carries no
score or recommendation field: it can only phrase the summary/strengths/weaknesses using the
deterministic data it's given (see :mod:`app.services.report_narrative`).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from app.domain.evaluation import (
    AnswerEvidenceType,
    EvaluationDecision,
    EvidenceStrength,
    evidence_label,
    evidence_strength_for_score,
)
from app.domain.interview_plan import QuestionCategory

# Re-exported for backward compatibility: `EvidenceStrength`/`evidence_strength_for_score`
# used to be defined here, but now live in `app.domain.evaluation` (moved so
# `resolve_follow_up_decision` there can reuse them without this module importing back from
# `app.domain.evaluation`, which already imports `EvaluationDecision` from it - see that
# module's docstring). Every existing `from app.domain.report import EvidenceStrength` /
# `evidence_strength_for_score` import keeps working unchanged. `AnswerEvidenceType`/
# `evidence_label` are re-exported the same way for the same reason.
__all__ = [
    "AnswerEvidenceType",
    "CompetencyAssessment",
    "EvidenceStrength",
    "InterviewReport",
    "QuestionEvaluationSummary",
    "Recommendation",
    "ReportNarrative",
    "evidence_label",
    "evidence_strength_for_score",
]


class Recommendation(StrEnum):
    STRONG_HIRE = "strong_hire"
    HIRE = "hire"
    CONSIDER = "consider"
    NO_HIRE = "no_hire"


class QuestionEvaluationSummary(BaseModel):
    """The final (last-attempt) evaluation of one interview question.

    A question that received a follow-up has more than one answer turn in the interview
    history; this summarises only the LAST turn, since that is the answer that actually
    determined whether the interview advanced (see
    :func:`app.services.report_scoring.build_question_evaluations`). ``score``/``decision``
    are ``None`` when that turn was never evaluated (e.g. a blank answer) - never guessed.
    """

    target_id: str = Field(
        default="",
        description=(
            "The coverage target this summarises, by id - the single source of truth for "
            "'was this target reached?' (see "
            "app.services.report_scoring.build_unassessed_required_targets). Distinct from "
            "`question_id`, which identifies the TURN shown to the candidate and is the "
            "follow-up's own id when the last turn was a follow-up. Conflating the two is "
            "what previously let a target that was asked, answered and scored also appear "
            "under 'required, never reached'. Defaults to empty only for hand-built/legacy "
            "summaries; every summary this codebase builds sets it."
        ),
    )
    question_id: str
    question: str
    category: QuestionCategory
    target: str
    candidate_answer: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    decision: EvaluationDecision | None = None
    evidence_type: AnswerEvidenceType | None = Field(
        default=None,
        description="None when the turn was never evaluated (e.g. a blank answer) - never guessed.",
    )
    evidence: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    assessment_method: Literal["direct", "cross_target"] = Field(
        default="direct",
        description=(
            "How this target's evidence was gathered - 'direct' means a question was asked "
            "specifically about it; 'cross_target' means it was never asked directly, but the "
            "candidate volunteered meaningful evidence for it while answering a different "
            "target's question (see app.services.cross_target_evidence). Orthogonal to "
            "evidence_type/evidence_label, which describe what the evidence shows, not how it "
            "was gathered - a target can be strongly demonstrated either way."
        ),
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evidence_strength(self) -> EvidenceStrength:
        """Always derived from ``score`` - never independently settable, so it can't drift."""
        return evidence_strength_for_score(self.score)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evidence_label(self) -> str:
        """Human-readable evidence label, primarily driven by ``evidence_type`` - see
        ``app.domain.evaluation.evidence_label`` for why this is more precise than
        ``evidence_strength`` alone for display purposes."""
        return evidence_label(self.evidence_type, self.score)


class CompetencyAssessment(BaseModel):
    """Aggregated assessment for one target (competency/technology/task), across every
    question that targeted it. ``score`` is ``None`` if none of its questions were evaluated -
    represented explicitly rather than guessed at."""

    name: str
    category: QuestionCategory
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_type: AnswerEvidenceType | None = Field(
        default=None,
        description=(
            "The evidence type of the LAST question evaluated for this target (mirrors "
            "build_question_evaluations' own last-turn-wins convention) - None if none of its "
            "questions were evaluated."
        ),
    )
    evidence: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    assessment_method: Literal["direct", "cross_target"] = Field(
        default="direct",
        description=(
            "The assessment_method of the LAST question evaluated for this target (mirrors "
            "evidence_type's own last-turn-wins convention) - see "
            "QuestionEvaluationSummary.assessment_method for what this distinguishes."
        ),
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evidence_strength(self) -> EvidenceStrength:
        """Always derived from ``score`` - never independently settable, so it can't drift."""
        return evidence_strength_for_score(self.score)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evidence_label(self) -> str:
        """Human-readable evidence label, primarily driven by ``evidence_type`` - see
        ``app.domain.evaluation.evidence_label`` for why this is more precise than
        ``evidence_strength`` alone for display purposes."""
        return evidence_label(self.evidence_type, self.score)


class ReportNarrative(BaseModel):
    """Structured LLM output: concise narrative synthesis only - no score, no recommendation.

    The LLM only rephrases/condenses the deterministic strengths/weaknesses/evidence it is
    given (see :class:`app.services.report_narrative.ReportNarrativeService`); it has no field
    through which it could influence the report's score or recommendation, and no
    chain-of-thought or hidden reasoning is requested or stored.
    """

    summary: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


class InterviewReport(BaseModel):
    """Evidence-based interview report. See :mod:`app.services.report_generation`."""

    interview_id: str
    job_id: str
    overall_score: float = Field(ge=0.0, le=1.0)
    recommendation: Recommendation
    summary: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    competencies: list[CompetencyAssessment] = Field(default_factory=list)
    question_evaluations: list[QuestionEvaluationSummary] = Field(default_factory=list)
    unassessed_required_targets: list[str] = Field(
        default_factory=list,
        description=(
            "Required coverage targets from the plan (see InterviewPlan.coverage_targets) "
            "that this adaptive interview never reached before it ended - distinct from a "
            "target that WAS asked about but produced insufficient evidence (that shows up in "
            "`competencies` with a low evidence_strength/evidence_label instead). An entry "
            "here means literally no question was ever asked or evidence ever volunteered "
            "about it - it must never be read as 'the candidate failed this' or as evidence of "
            "any kind; the interview simply ended (adaptively) before reaching it."
        ),
    )
    score_basis_note: str = Field(
        default=(
            "Based on assessed evidence only. Unassessed requirements are not treated as "
            "failures."
        ),
        description=(
            "Fixed, deterministic clarification of what overall_score/recommendation mean - "
            "never LLM-generated, always present regardless of whether unassessed_required_"
            "targets is empty - meant to sit next to the score in the UI so a score (e.g. "
            "'88%, Strong Hire') is never misread as 'the candidate satisfies 88% of the "
            "role's requirements'. See app.services.report_scoring.compute_overall_score for "
            "why the score is scoped to assessed evidence only."
        ),
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def overall_evidence_strength(self) -> EvidenceStrength:
        """Always derived from ``overall_score`` - never independently settable."""
        return evidence_strength_for_score(self.overall_score)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def completion_reason(self) -> Literal["sufficient_evidence", "budget_exhausted"]:
        """Why the adaptive interview stopped - derived, not separately tracked state.

        The current termination architecture (``app.services.target_selection.
        select_next_target``) has exactly two ways to end: every required target got a turn
        (a category's *effective* budget can never fall below its required-target count - see
        that module - and required targets always outrank preferred ones globally), or the
        interview's ``total_budget`` safety cap was hit first. Consequently a required target
        can be left in ``unassessed_required_targets`` *only* when the safety cap fired before
        every required target could be reached - there is no other path in the current
        architecture that strands a required target. That makes this derivable with no new
        graph state: empty ``unassessed_required_targets`` means every required target was
        reached (``sufficient_evidence``); a non-empty list means the interview ran out of
        budget before it could reach all of them (``budget_exhausted``). Never implies the
        interview assessed *every* target in the plan - only that no required one was skipped
        for lack of a turn.
        """
        return "sufficient_evidence" if not self.unassessed_required_targets else "budget_exhausted"
