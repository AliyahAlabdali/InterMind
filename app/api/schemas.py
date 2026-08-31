"""Request and response models for the HTTP layer (kept separate from domain models)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.job import JobSpec
from app.repositories.ports import StoredJob


class AnalyzeJobRequest(BaseModel):
    job_description: str = Field(min_length=1, description="Raw job description text.")


class JobResponse(BaseModel):
    id: str
    job_description: str
    job_spec: JobSpec
    created_at: datetime

    @classmethod
    def from_stored(cls, stored: StoredJob) -> JobResponse:
        return cls.model_validate(stored.model_dump())
