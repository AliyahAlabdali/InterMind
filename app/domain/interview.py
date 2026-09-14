"""Interview state.

Originally an intentionally minimal, behaviour-free skeleton (Milestone 1) so a later
milestone could wrap the interview lifecycle in a stateful orchestrator without restructuring
the domain. Milestone 4 does that wrapping: :mod:`app.agents.interview_graph` owns the actual
LangGraph state/transitions, and :mod:`app.services.interview_session` maps its state onto this
model - the API layer and callers outside the graph only ever see :class:`InterviewState`.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class InterviewStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class InterviewState(BaseModel):
    """Serialisable state for a single interview session."""

    job_id: str
    status: InterviewStatus = InterviewStatus.NOT_STARTED
    turn_index: int = 0
    history: list[dict] = Field(default_factory=list)
    current_question_id: str | None = None
    current_question_text: str | None = None
    asked_question_ids: list[str] = Field(default_factory=list)