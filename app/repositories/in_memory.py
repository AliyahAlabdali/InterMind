"""In-memory :class:`JobRepository`. Sufficient for Milestone 1; not durable."""

from __future__ import annotations

from app.core.exceptions import JobNotFound
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
