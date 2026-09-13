"""In-memory repositories. Sufficient for Milestone 1-3; not durable."""

from __future__ import annotations

from app.core.exceptions import InterviewPlanNotFound, JobNotFound
from app.domain.interview_plan import InterviewPlan
from app.repositories.ports import StoredJob


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
