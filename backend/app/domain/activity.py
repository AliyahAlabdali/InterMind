"""Interview activity events - the recruiter-facing record of what the adaptive interview
actually did, as it did it.

Deliberately a *derived* log, not a new source of truth: every event here is recorded from a
state transition the interview graph had already produced and the API layer had already seen
(see ``app.api.routes.interviews``). Nothing in the interview loop, the evaluator, or the report
pipeline reads this back - deleting the whole log would change no interview behaviour and no
score. That is what keeps it a genuinely additive feature rather than a second, competing model
of interview progress.

Events are recorded at the route layer rather than inside the LangGraph nodes on purpose: the
graph's job is to conduct the interview, and threading an activity recorder through it would
couple orchestration to presentation for no behavioural gain.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class ActivityType(StrEnum):
    """What happened. Each value maps to a real, observable transition:

    - ``interview_started``: a recruiter minted a session (``POST /interviews``).
    - ``evidence_detected``: an evaluated answer produced non-empty evidence for its target.
    - ``follow_up_generated``: the evaluator decided the answer warranted going deeper.
    - ``interview_completed``: the graph reached its finished state.
    """

    INTERVIEW_STARTED = "interview_started"
    EVIDENCE_DETECTED = "evidence_detected"
    FOLLOW_UP_GENERATED = "follow_up_generated"
    INTERVIEW_COMPLETED = "interview_completed"


class ActivityEvent(BaseModel):
    """One recorded moment in an interview.

    ``target`` is the coverage target the event concerns (e.g. "PostgreSQL") where the event
    type has one - ``None`` for whole-interview events like start/completion. It is never
    inferred: it comes from the turn the event was derived from.
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    type: ActivityType
    interview_id: str
    job_id: str
    candidate_name: str
    target: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
