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

from pydantic import BaseModel, Field

from app.domain.evaluation import EvaluationDecision
from app.domain.interview_plan import QuestionCategory


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

    question_id: str
    question: str
    category: QuestionCategory
    target: str
    candidate_answer: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    decision: EvaluationDecision | None = None
    evidence: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


class CompetencyAssessment(BaseModel):
    """Aggregated assessment for one target (competency/technology/task), across every
    question that targeted it. ``score`` is ``None`` if none of its questions were evaluated -
    represented explicitly rather than guessed at."""

    name: str
    category: QuestionCategory
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


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
