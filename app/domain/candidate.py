"""Domain model for a candidate invited to interview.

Deliberately minimal for this milestone (name/email/id only - see the recruiter-workflow
architecture review): a `Candidate` is a distinct entity from an `InterviewSession` because one
person could, in principle, be invited to more than one interview (or retake one), and because
keeping identity separate from session/progress state is what makes a future move to a real
database (one `candidates` table, one `interview_sessions` table with a foreign key) a
straightforward migration rather than a redesign.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field


class Candidate(BaseModel):
    """A person invited to complete an interview."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    email: str
