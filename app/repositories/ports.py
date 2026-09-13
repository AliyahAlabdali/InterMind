"""Persistence boundaries for analysed jobs and their interview plans."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from app.domain.interview_plan import InterviewPlan
from app.domain.job import JobSpec


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
