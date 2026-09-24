"""In-memory repositories. Sufficient for Milestone 1-3; not durable."""

from __future__ import annotations

from app.core.exceptions import (
    CandidateNotFound,
    InterviewNotFound,
    InterviewPlanNotFound,
    InterviewReportNotFound,
    JobNotFound,
    RecruiterEmailTaken,
)
from app.domain.activity import ActivityEvent
from app.domain.candidate import Candidate
from app.domain.interview_plan import InterviewPlan
from app.domain.recruiter import Recruiter, normalize_email
from app.domain.report import InterviewReport
from app.repositories.ports import InterviewSession, StoredJob


class InMemoryJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, StoredJob] = {}

    async def add(self, job: StoredJob) -> StoredJob:
        self._jobs[job.id] = job
        return job

    async def get(self, job_id: str) -> StoredJob:
        try:
            return self._jobs[job_id]
        except KeyError:
            raise JobNotFound(job_id) from None

    async def get_for_recruiter(self, job_id: str, recruiter_id: str) -> StoredJob:
        job = self._jobs.get(job_id)
        # Another recruiter's job is reported exactly like a missing one - see
        # app.repositories.sql for why.
        if job is None or job.recruiter_id != recruiter_id:
            raise JobNotFound(job_id)
        return job

    async def list_by_recruiter(self, recruiter_id: str) -> list[StoredJob]:
        return [
            job
            for job in sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            if job.recruiter_id == recruiter_id
        ]

    async def list_all(self) -> list[StoredJob]:
        return list(reversed(self._jobs.values()))


class InMemoryRecruiterRepository:
    """Recruiter accounts, in memory. Tests only - real deployments use the SQL repository,
    because an account that does not survive a restart is not an account."""

    def __init__(self) -> None:
        self._by_id: dict[str, Recruiter] = {}
        self._by_email: dict[str, str] = {}

    async def add(self, recruiter: Recruiter) -> Recruiter:
        email = normalize_email(recruiter.email)
        if email in self._by_email:
            raise RecruiterEmailTaken("An account with that email already exists.")
        stored = recruiter.model_copy(update={"email": email})
        self._by_id[stored.id] = stored
        self._by_email[email] = stored.id
        return stored

    async def get_by_email(self, email: str) -> Recruiter | None:
        recruiter_id = self._by_email.get(normalize_email(email))
        return self._by_id.get(recruiter_id) if recruiter_id else None

    async def get(self, recruiter_id: str) -> Recruiter | None:
        return self._by_id.get(recruiter_id)


class InMemoryCandidateRepository:
    def __init__(self) -> None:
        self._candidates: dict[str, Candidate] = {}

    async def add(self, candidate: Candidate) -> Candidate:
        self._candidates[candidate.id] = candidate
        return candidate

    async def get(self, candidate_id: str) -> Candidate:
        try:
            return self._candidates[candidate_id]
        except KeyError:
            raise CandidateNotFound(candidate_id) from None


class InMemoryInterviewPlanRepository:
    def __init__(self) -> None:
        self._plans: dict[str, InterviewPlan] = {}

    async def add(self, plan: InterviewPlan) -> InterviewPlan:
        self._plans[plan.job_id] = plan
        return plan

    async def get(self, job_id: str) -> InterviewPlan:
        try:
            return self._plans[job_id]
        except KeyError:
            raise InterviewPlanNotFound(job_id) from None


class InMemoryInterviewSessionRepository:
    def __init__(self, jobs: InMemoryJobRepository | None = None) -> None:
        self._sessions: dict[str, InterviewSession] = {}
        # Ownership is derived through the session's job, exactly as the SQL repository joins
        # to `jobs`. Optional so a test can build a bare session store; without it,
        # `get_for_recruiter` denies everything rather than guessing.
        self._jobs: dict[str, StoredJob] | None = jobs._jobs if jobs is not None else None

    async def add(self, session: InterviewSession) -> InterviewSession:
        self._sessions[session.id] = session
        return session

    async def get(self, interview_id: str) -> InterviewSession:
        try:
            return self._sessions[interview_id]
        except KeyError:
            raise InterviewNotFound(interview_id) from None

    async def get_for_recruiter(self, interview_id: str, recruiter_id: str) -> InterviewSession:
        session = self._sessions.get(interview_id)
        if session is None:
            raise InterviewNotFound(interview_id)
        job = (self._jobs or {}).get(session.job_id)
        if job is None or job.recruiter_id != recruiter_id:
            raise InterviewNotFound(interview_id)
        return session

    async def list_by_job(self, job_id: str) -> list[InterviewSession]:
        return [s for s in self._sessions.values() if s.job_id == job_id]


class InMemoryActivityRepository:
    """Append-only, newest-last internally; ``list_recent`` reverses so callers get newest
    first. Bounded so a long-running process can't grow it without limit - this is a display
    feed, not an audit trail, and nothing reads it back for correctness."""

    _MAX_EVENTS = 500

    def __init__(self, jobs: InMemoryJobRepository | None = None) -> None:
        self._events: list[ActivityEvent] = []
        # As above: the feed is scoped by the owning job.
        self._jobs: dict[str, StoredJob] | None = jobs._jobs if jobs is not None else None

    async def add(self, event: ActivityEvent) -> ActivityEvent:
        self._events.append(event)
        if len(self._events) > self._MAX_EVENTS:
            del self._events[: len(self._events) - self._MAX_EVENTS]
        return event

    async def list_recent_for_recruiter(
        self, recruiter_id: str, limit: int = 20
    ) -> list[ActivityEvent]:
        owned = {
            job_id
            for job_id, job in (self._jobs or {}).items()
            if job.recruiter_id == recruiter_id
        }
        return [e for e in reversed(self._events) if e.job_id in owned][:limit]

    async def list_recent(self, limit: int = 20) -> list[ActivityEvent]:
        if limit <= 0:
            return []
        return list(reversed(self._events[-limit:]))


class InMemoryInterviewReportRepository:
    def __init__(self) -> None:
        self._reports: dict[str, InterviewReport] = {}

    async def add(self, report: InterviewReport) -> InterviewReport:
        self._reports[report.interview_id] = report
        return report

    async def get(self, interview_id: str) -> InterviewReport:
        try:
            return self._reports[interview_id]
        except KeyError:
            raise InterviewReportNotFound(interview_id) from None
