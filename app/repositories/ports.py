"""Persistence boundaries for analysed jobs and their interview plans."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from app.domain.candidate import Candidate
from app.domain.interview_plan import InterviewPlan
from app.domain.job import JobSpec
from app.domain.report import InterviewReport


class StoredJob(BaseModel):
    """A persisted job: the original text plus its structured analysis."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    job_description: str
    job_spec: JobSpec
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JobRepository(Protocol):
    async def add(self, job: StoredJob) -> StoredJob:
        """Persist ``job`` and return it."""
        ...

    async def get(self, job_id: str) -> StoredJob:
        """Return the stored job.

        Raises:
            app.core.exceptions.JobNotFound: no job with that id.
        """
        ...

    async def list_all(self) -> list[StoredJob]:
        """Return every stored job, most-recently-created first.

        Backs the recruiter dashboard (see the recruiter-workflow architecture review) - the
        dashboard's list of interviews/roles is real backend state, not a client-side cache.
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

    async def list_by_job(self, job_id: str) -> list[InterviewSession]:
        """Return every interview session created for ``job_id``, in creation order.

        Backs the recruiter's candidate table for one interview/role (see the
        recruiter-workflow architecture review) - the recruiter must be able to see every
        candidate associated with a job without any client-side tracking.
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
