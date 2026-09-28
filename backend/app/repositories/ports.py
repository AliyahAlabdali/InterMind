"""Persistence boundaries for analysed jobs and their interview plans."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from app.domain.activity import ActivityEvent
from app.domain.candidate import Candidate
from app.domain.interview_plan import InterviewPlan
from app.domain.job import JobSpec
from app.domain.recruiter import Recruiter
from app.domain.report import InterviewReport


class StoredJob(BaseModel):
    """A persisted job: the original text plus its structured analysis.

    ``recruiter_id`` is the authoritative ownership edge for the whole product - every other
    recruiter-private resource derives its owner by reaching a job (see ``app.db.models``). It
    is set from the authenticated session on the server and is never accepted from a request
    body.
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    recruiter_id: str
    job_description: str
    job_spec: JobSpec
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RecruiterRepository(Protocol):
    """Recruiter accounts. The only store in the product that holds a credential."""

    async def add(self, recruiter: Recruiter) -> Recruiter:
        """Persist ``recruiter`` and return it.

        Raises:
            app.core.exceptions.RecruiterEmailTaken: that normalised email already exists.
                Raised from the database's unique constraint rather than a prior lookup, so two
                concurrent signups cannot both pass a check and both insert.
        """
        ...

    async def get_by_email(self, email: str) -> Recruiter | None:
        """Return the recruiter with this normalised email, or ``None``. Never raises for a
        missing account: sign-in must treat "no such email" and "wrong password" identically."""
        ...

    async def get(self, recruiter_id: str) -> Recruiter | None:
        """Return the recruiter, or ``None`` if the id is unknown (e.g. a session outliving a
        deleted account)."""
        ...


class JobRepository(Protocol):
    async def add(self, job: StoredJob) -> StoredJob:
        """Persist ``job`` and return it."""
        ...

    async def get(self, job_id: str) -> StoredJob:
        """Return the stored job, regardless of owner.

        Callers that act for a recruiter must use :meth:`get_for_recruiter` instead - this one
        backs the deliberately public candidate-facing lookup.

        Raises:
            app.core.exceptions.JobNotFound: no job with that id.
        """
        ...

    async def get_for_recruiter(self, job_id: str, recruiter_id: str) -> StoredJob:
        """Return the job only if ``recruiter_id`` owns it.

        Ownership is enforced in the query, not by fetching and then comparing in Python, and a
        job owned by someone else raises the same ``JobNotFound`` as one that does not exist -
        so a probing request cannot tell the two apart.

        Raises:
            app.core.exceptions.JobNotFound: unknown id, or owned by another recruiter.
        """
        ...

    async def list_by_recruiter(self, recruiter_id: str) -> list[StoredJob]:
        """Return this recruiter's jobs, most-recently-created first.

        Replaces a ``list_all`` that returned every job in the deployment - which was correct
        when there was one recruiter and is a cross-tenant leak now that there are many.
        """
        ...


class CandidateRepository(Protocol):
    async def add(self, candidate: Candidate) -> Candidate:
        """Persist ``candidate`` and return it."""
        ...

    async def get(self, candidate_id: str) -> Candidate:
        """Return the stored candidate.

        Raises:
            app.core.exceptions.CandidateNotFound: no candidate with that id.
        """
        ...


class InterviewPlanRepository(Protocol):
    """Stores at most one interview plan per job id (re-planning overwrites it)."""

    async def add(self, plan: InterviewPlan) -> InterviewPlan:
        """Persist ``plan`` (keyed by ``plan.job_id``) and return it."""
        ...

    async def get(self, job_id: str) -> InterviewPlan:
        """Return the stored interview plan for ``job_id``.

        Raises:
            app.core.exceptions.InterviewPlanNotFound: no plan exists for that job id.
        """
        ...


class InterviewSession(BaseModel):
    """Tracks that an interview id is a valid, started LangGraph thread for a job, and which
    candidate it belongs to.

    A job can have more than one interview session (e.g. multiple candidates, or a retake), so
    this is keyed by its own ``id`` rather than by ``job_id``. The actual interview progress
    lives in the LangGraph checkpointer (``id`` doubles as the graph's ``thread_id``) - this
    record only lets the API layer validate an interview id, recover which job/plan it belongs
    to, and (see the recruiter-workflow architecture review) which candidate is taking it.
    ``candidate_id`` defaults to ``""`` only for legacy/test fixtures constructed without a
    candidate; every session created through :meth:`app.services.interview_session.
    InterviewSessionService.start` has a real one.

    ``access_token`` is this session's own opaque, unguessable credential (see
    ``app.api.auth``'s ``require_candidate_access``) - it is what scopes a candidate's access
    to exactly this interview and no other, so a leaked/guessed interview id alone is not
    enough to read or act on someone else's session. Milestone-4-level access boundary, not
    production auth; every session gets a freshly random one, never reused or guessable from
    the session id.
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    job_id: str
    candidate_id: str = ""
    access_token: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InterviewSessionRepository(Protocol):
    async def add(self, session: InterviewSession) -> InterviewSession:
        """Persist ``session`` and return it."""
        ...

    async def get(self, interview_id: str) -> InterviewSession:
        """Return the stored interview session.

        Raises:
            app.core.exceptions.InterviewNotFound: no session with that id.
        """
        ...

    async def get_for_recruiter(self, interview_id: str, recruiter_id: str) -> InterviewSession:
        """Return the session only if it belongs to a job ``recruiter_id`` owns.

        Raises:
            app.core.exceptions.InterviewNotFound: unknown id, or another recruiter's.
        """
        ...

    async def list_by_job(self, job_id: str) -> list[InterviewSession]:
        """Return every interview session created for ``job_id``, in creation order.

        Backs the recruiter's candidate table for one interview/role (see the
        recruiter-workflow architecture review) - the recruiter must be able to see every
        candidate associated with a job without any client-side tracking.
        """
        ...


class ActivityRepository(Protocol):
    """Append-only log of interview activity (see ``app.domain.activity``).

    Nothing in the interview or report pipeline reads this back - it exists purely so the
    recruiter workspace can show what the adaptive interview has been doing, without the
    frontend inventing events it has no way to know about.
    """

    async def add(self, event: ActivityEvent) -> ActivityEvent:
        """Append ``event`` to the log and return it."""
        ...

    async def list_recent_for_recruiter(
        self, recruiter_id: str, limit: int = 20
    ) -> list[ActivityEvent]:
        """Return this recruiter's most recent events, newest first, capped at ``limit``.

        Scoped by joining through the event's job to its owner - the feed names candidates and
        the targets they were assessed on, so an unscoped version would hand every recruiter a
        live view of everyone else's interviews.
        """
        ...


class InterviewReportRepository(Protocol):
    """Stores at most one report per interview id - a completed interview's report is
    generated once and returned unchanged on every later request (see
    ``GET /interviews/{id}/report``)."""

    async def add(self, report: InterviewReport) -> InterviewReport:
        """Persist ``report`` (keyed by ``report.interview_id``) and return it."""
        ...

    async def get(self, interview_id: str) -> InterviewReport:
        """Return the stored report for ``interview_id``.

        Raises:
            app.core.exceptions.InterviewReportNotFound: no report exists yet for that id.
        """
        ...
