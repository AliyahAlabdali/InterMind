"""Persistence boundary for analysed jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

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
