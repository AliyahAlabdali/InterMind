"""PostgreSQL implementations of the repository ports.

The only module that knows the application is backed by a database. Everything above it talks to
the ``Protocol`` classes in ``.ports``, so the domain and service layers are unchanged by this
existing at all - and the in-memory implementations remain valid for tests.

Two rules hold throughout:

1. **Ownership is enforced in the query.** A ``…_for_recruiter`` method filters by owner in SQL
   rather than fetching a row and comparing in Python. There is no code path where a row is
   loaded first and checked second, because that is the path where someone eventually forgets
   the check.
2. **A resource owned by someone else is indistinguishable from one that does not exist.** Both
   raise the same ``NotFound``. Returning 403 for "exists but not yours" would confirm the
   existence of other recruiters' jobs to anyone willing to enumerate ids.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.exceptions import (
    CandidateNotFound,
    InterviewNotFound,
    InterviewPlanNotFound,
    InterviewReportNotFound,
    JobNotFound,
    RecruiterEmailTaken,
)
from app.db.models import (
    ActivityEventRow,
    CandidateRow,
    InterviewPlanRow,
    InterviewReportRow,
    InterviewSessionRow,
    JobRow,
    RecruiterRow,
)
from app.domain.activity import ActivityEvent
from app.domain.candidate import Candidate
from app.domain.interview_plan import InterviewPlan
from app.domain.recruiter import Recruiter, normalize_email
from app.domain.report import InterviewReport
from app.repositories.ports import InterviewSession, StoredJob


class _SessionScoped:
    """Base: each call opens its own short-lived session and transaction."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sessions = session_factory


class SqlRecruiterRepository(_SessionScoped):
    async def add(self, recruiter: Recruiter) -> Recruiter:
        row = RecruiterRow(
            id=recruiter.id,
            email=normalize_email(recruiter.email),
            password_hash=recruiter.password_hash,
            created_at=recruiter.created_at,
        )
        async with self._sessions() as session:
            session.add(row)
            try:
                await session.commit()
            except IntegrityError as exc:
                # The unique index is the authority, not a prior SELECT: two concurrent signups
                # for the same address both pass a check-then-insert, and only this loses.
                await session.rollback()
                raise RecruiterEmailTaken(
                    "An account with that email already exists."
                ) from exc
        return recruiter

    async def get_by_email(self, email: str) -> Recruiter | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(RecruiterRow).where(RecruiterRow.email == normalize_email(email))
            )
        return _recruiter(row) if row else None

    async def get(self, recruiter_id: str) -> Recruiter | None:
        async with self._sessions() as session:
            row = await session.get(RecruiterRow, recruiter_id)
        return _recruiter(row) if row else None


class SqlJobRepository(_SessionScoped):
    async def add(self, job: StoredJob) -> StoredJob:
        async with self._sessions() as session:
            session.add(
                JobRow(
                    id=job.id,
                    recruiter_id=job.recruiter_id,
                    job_description=job.job_description,
                    job_spec=job.job_spec.model_dump(mode="json"),
                    created_at=job.created_at,
                )
            )
            await session.commit()
        return job

    async def get(self, job_id: str) -> StoredJob:
        async with self._sessions() as session:
            row = await session.get(JobRow, job_id)
        if row is None:
            raise JobNotFound(job_id)
        return _job(row)

    async def get_for_recruiter(self, job_id: str, recruiter_id: str) -> StoredJob:
        async with self._sessions() as session:
            row = await session.scalar(
                select(JobRow).where(
                    JobRow.id == job_id, JobRow.recruiter_id == recruiter_id
                )
            )
        if row is None:
            # Same error as a genuinely unknown id - see the module docstring.
            raise JobNotFound(job_id)
        return _job(row)

    async def list_by_recruiter(self, recruiter_id: str) -> list[StoredJob]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(JobRow)
                .where(JobRow.recruiter_id == recruiter_id)
                .order_by(JobRow.created_at.desc())
            )
            return [_job(row) for row in rows]


class SqlInterviewPlanRepository(_SessionScoped):
    async def add(self, plan: InterviewPlan) -> InterviewPlan:
        async with self._sessions() as session:
            existing = await session.get(InterviewPlanRow, plan.job_id)
            payload = plan.model_dump(mode="json")
            if existing is None:
                session.add(InterviewPlanRow(job_id=plan.job_id, plan=payload))
            else:
                existing.plan = payload  # re-planning overwrites, per the port's contract
            await session.commit()
        return plan

    async def get(self, job_id: str) -> InterviewPlan:
        async with self._sessions() as session:
            row = await session.get(InterviewPlanRow, job_id)
        if row is None:
            raise InterviewPlanNotFound(job_id)
        return InterviewPlan.model_validate(row.plan)


class SqlCandidateRepository(_SessionScoped):
    async def add(self, candidate: Candidate) -> Candidate:
        async with self._sessions() as session:
            session.add(
                CandidateRow(
                    id=candidate.id, name=candidate.name, email=candidate.email or ""
                )
            )
            await session.commit()
        return candidate

    async def get(self, candidate_id: str) -> Candidate:
        async with self._sessions() as session:
            row = await session.get(CandidateRow, candidate_id)
        if row is None:
            raise CandidateNotFound(candidate_id)
        return Candidate(id=row.id, name=row.name, email=row.email)


class SqlInterviewSessionRepository(_SessionScoped):
    async def add(self, session_record: InterviewSession) -> InterviewSession:
        async with self._sessions() as session:
            session.add(
                InterviewSessionRow(
                    id=session_record.id,
                    job_id=session_record.job_id,
                    candidate_id=session_record.candidate_id or "",
                    access_token=session_record.access_token,
                    created_at=session_record.created_at,
                )
            )
            await session.commit()
        return session_record

    async def get(self, interview_id: str) -> InterviewSession:
        async with self._sessions() as session:
            row = await session.get(InterviewSessionRow, interview_id)
        if row is None:
            raise InterviewNotFound(interview_id)
        return _interview_session(row)

    async def get_for_recruiter(
        self, interview_id: str, recruiter_id: str
    ) -> InterviewSession:
        async with self._sessions() as session:
            row = await session.scalar(
                select(InterviewSessionRow)
                .join(JobRow, JobRow.id == InterviewSessionRow.job_id)
                .where(
                    InterviewSessionRow.id == interview_id,
                    JobRow.recruiter_id == recruiter_id,
                )
            )
        if row is None:
            raise InterviewNotFound(interview_id)
        return _interview_session(row)

    async def list_by_job(self, job_id: str) -> list[InterviewSession]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(InterviewSessionRow)
                .where(InterviewSessionRow.job_id == job_id)
                .order_by(InterviewSessionRow.created_at)
            )
            return [_interview_session(row) for row in rows]


class SqlActivityRepository(_SessionScoped):
    async def add(self, event: ActivityEvent) -> ActivityEvent:
        async with self._sessions() as session:
            session.add(
                ActivityEventRow(
                    id=event.id,
                    type=str(event.type),
                    interview_id=event.interview_id,
                    job_id=event.job_id,
                    candidate_name=event.candidate_name,
                    target=event.target,
                    created_at=event.created_at,
                )
            )
            await session.commit()
        return event

    async def list_recent_for_recruiter(
        self, recruiter_id: str, limit: int = 20
    ) -> list[ActivityEvent]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(ActivityEventRow)
                .join(JobRow, JobRow.id == ActivityEventRow.job_id)
                .where(JobRow.recruiter_id == recruiter_id)
                .order_by(ActivityEventRow.created_at.desc())
                .limit(limit)
            )
            return [
                ActivityEvent(
                    id=row.id,
                    type=row.type,
                    interview_id=row.interview_id,
                    job_id=row.job_id,
                    candidate_name=row.candidate_name,
                    target=row.target,
                    created_at=row.created_at,
                )
                for row in rows
            ]


class SqlInterviewReportRepository(_SessionScoped):
    async def add(self, report: InterviewReport) -> InterviewReport:
        async with self._sessions() as session:
            payload = report.model_dump(mode="json")
            existing = await session.get(InterviewReportRow, report.interview_id)
            if existing is None:
                session.add(
                    InterviewReportRow(interview_id=report.interview_id, report=payload)
                )
            else:
                existing.report = payload
            await session.commit()
        return report

    async def get(self, interview_id: str) -> InterviewReport:
        async with self._sessions() as session:
            row = await session.get(InterviewReportRow, interview_id)
        if row is None:
            raise InterviewReportNotFound(interview_id)
        return InterviewReport.model_validate(row.report)


# --- row -> domain ---------------------------------------------------------------------


def _recruiter(row: RecruiterRow) -> Recruiter:
    return Recruiter(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        created_at=row.created_at,
    )


def _job(row: JobRow) -> StoredJob:
    return StoredJob(
        id=row.id,
        recruiter_id=row.recruiter_id,
        job_description=row.job_description,
        job_spec=row.job_spec,
        created_at=row.created_at,
    )


def _interview_session(row: InterviewSessionRow) -> InterviewSession:
    return InterviewSession(
        id=row.id,
        job_id=row.job_id,
        candidate_id=row.candidate_id,
        access_token=row.access_token,
        created_at=row.created_at,
    )
