"""Interview state skeleton.

Intentionally minimal and behaviour-free for Milestone 1. It exists now so a later
milestone can wrap the interview lifecycle in a stateful orchestrator (e.g. LangGraph)
by treating this model as the graph state and adding pure transition functions - without
restructuring the domain or the service interfaces.
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
