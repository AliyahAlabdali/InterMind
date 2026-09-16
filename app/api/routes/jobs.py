"""Job endpoints: submit a job description, retrieve a stored analysis.

Access note: these endpoints are NOT covered by the Milestone 4 access boundary (see
``app.api.auth``) - they carry no ``require_recruiter_access``/``require_candidate_access``
dependency and are fully public. That boundary's guarantee is specifically the interview-level
candidate/recruiter split (a candidate's own interview vs. recruiter-only report/candidate-
listing/start); resource-level authorization for jobs/job-analysis is Milestone 6-B
productionization work. Do not assume or claim these are protected.
"""

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


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(
    repo: JobRepository = Depends(get_job_repository),
) -> list[JobResponse]:
    """List every analyzed job/role, most-recently-created first.

    Backs the recruiter dashboard (see the recruiter-workflow architecture review) - the list
    of interviews/roles a recruiter sees is real backend state, not a client-side cache.
    """
    stored_jobs = await repo.list_all()
    return [JobResponse.from_stored(stored) for stored in stored_jobs]
