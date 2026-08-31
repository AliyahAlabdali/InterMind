"""Job endpoints: submit a job description, retrieve a stored analysis."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import get_jd_analysis_service, get_job_repository
from app.api.schemas import AnalyzeJobRequest, JobResponse
from app.repositories.ports import JobRepository, StoredJob
from app.services.jd_analysis import JDAnalysisService

router = APIRouter(tags=["jobs"])


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: AnalyzeJobRequest,
    service: JDAnalysisService = Depends(get_jd_analysis_service),
    repo: JobRepository = Depends(get_job_repository),
) -> JobResponse:
    job_spec = await service.analyze(payload.job_description)
    stored = await repo.add(
        StoredJob(job_description=payload.job_description, job_spec=job_spec)
    )
    return JobResponse.from_stored(stored)


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    repo: JobRepository = Depends(get_job_repository),
) -> JobResponse:
    stored = await repo.get(job_id)
    return JobResponse.from_stored(stored)
