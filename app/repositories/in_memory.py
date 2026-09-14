"""In-memory repositories. Sufficient for Milestone 1-3; not durable."""

from __future__ import annotations

from app.core.exceptions import (
    InterviewNotFound,
    InterviewPlanNotFound,
    InterviewReportNotFound,
    JobNotFound,
)
from app.domain.interview_plan import InterviewPlan
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
    def __init__(self) -> None:
        self._sessions: dict[str, InterviewSession] = {}

    async def add(self, session: InterviewSession) -> InterviewSession:
        self._sessions[session.id] = session
        return session

    async def get(self, interview_id: str) -> InterviewSession:
        try:
            return self._sessions[interview_id]
        except KeyError:
            raise InterviewNotFound(interview_id) from None


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
