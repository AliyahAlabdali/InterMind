"""Domain model for LLM-based evaluation of one candidate answer.

Produced by :class:`app.services.answer_evaluation.AnswerEvaluationService` and consumed by
:mod:`app.agents.interview_graph` to decide whether to advance to the next question or ask a
follow-up. Fields are deliberately concise and evidence-based - no chain-of-thought or hidden
reasoning is ever requested from the LLM or stored here.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class EvaluationDecision(StrEnum):
    ADVANCE = "advance"
    FOLLOW_UP = "follow_up"


class AnswerEvaluation(BaseModel):
    """Structured, evidence-based evaluation of one candidate answer to one question."""

    score: float = Field(
        ge=0.0, le=1.0, description="0 (no relevant evidence) to 1 (strong, specific evidence)."
    )
    decision: EvaluationDecision
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(
        default_factory=list,
        description="Short quotes or close paraphrases from the answer supporting the score.",
    )
    follow_up_needed: bool
    follow_up_question: str | None = Field(
        default=None,
        description="Set only when follow_up_needed is true.",
    )

    @model_validator(mode="after")
    def _reconcile_follow_up(self) -> AnswerEvaluation:
        """``decision`` is authoritative: keep ``follow_up_needed``/``follow_up_question``
        consistent with it rather than raising on a minor LLM inconsistency."""
        follow_up = self.decision == EvaluationDecision.FOLLOW_UP
        if self.follow_up_needed != follow_up:
            self.follow_up_needed = follow_up
        if not follow_up:
            self.follow_up_question = None
        return self
