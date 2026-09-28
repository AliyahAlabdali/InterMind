"""Job endpoints: submit a job description, retrieve a stored analysis.

Access note
-----------
These endpoints are split rather than uniformly public, because the candidate interview needs
one of them and nothing else here.

- ``POST /jobs`` and ``GET /jobs`` are **recruiter-only and owner-scoped**. Creating a job is a
  write that also spends an LLM call on job-description analysis, and listing them returns roles
  with their full description - neither has any candidate use. ``GET /jobs`` answers from
  ``list_by_recruiter``, so a recruiter sees only their own.
- ``GET /jobs/{job_id}`` stays **public by design**, returning the reduced
  :class:`~app.api.schemas.PublicJobResponse`: the candidate's interview screen reads it to show
  which role they are interviewing for, before any token exists, and a candidate holds only
  their own interview's token - not a recruiter credential, and not one this route could scope
  against a job id. The raw ``job_description`` is deliberately not in that shape.

The boundary in ``app.api.auth`` is unchanged by this: recruiter-only operations stay
recruiter-only, and candidate access stays scoped to a candidate's own interview.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.auth import current_recruiter_id
from app.api.deps import get_jd_analysis_service, get_job_repository
from app.api.schemas import AnalyzeJobRequest, JobResponse, PublicJobResponse
from app.repositories.ports import JobRepository, StoredJob
from app.services.jd_analysis import JDAnalysisService

router = APIRouter(tags=["jobs"])


@router.post(
    "/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    payload: AnalyzeJobRequest,
    recruiter_id: str = Depends(current_recruiter_id),
    service: JDAnalysisService = Depends(get_jd_analysis_service),
    repo: JobRepository = Depends(get_job_repository),
) -> JobResponse:
    """Analyze a job description and store it against the signed-in recruiter.

    The owner comes from the session, never from the request. `AnalyzeJobRequest` has no
    `recruiter_id` field at all, so a client cannot even express the wish to create a job for
    somebody else.
    """
    job_spec = await service.analyze(payload.job_description)
    stored = await repo.add(
        StoredJob(
            recruiter_id=recruiter_id,
            job_description=payload.job_description,
            job_spec=job_spec,
        )
    )
    return JobResponse.from_stored(stored)


@router.get("/jobs/{job_id}", response_model=PublicJobResponse)
async def get_job(
    job_id: str,
    repo: JobRepository = Depends(get_job_repository),
) -> PublicJobResponse:
    """Read one job's public shape. Deliberately unauthenticated - the candidate interview
    screen needs it to name the role being interviewed for, and a candidate holds only their own
    interview's token.

    Returns ``PublicJobResponse``, not the full job: see that model for why the raw
    job-description text is no longer on a public endpoint.
    """
    stored = await repo.get(job_id)
    return PublicJobResponse.from_stored(stored)


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(
    recruiter_id: str = Depends(current_recruiter_id),
    repo: JobRepository = Depends(get_job_repository),
) -> list[JobResponse]:
    """List every analyzed job/role, most-recently-created first.

    Backs the recruiter dashboard (see the recruiter-workflow architecture review) - the list
    of interviews/roles a recruiter sees is real backend state, not a client-side cache. No
    candidate screen reads it. Scoped in the query to the signed-in recruiter: it used to
    return every role in the deployment, which was correct with one recruiter and is a
    cross-tenant leak with many.
    """
    stored_jobs = await repo.list_by_recruiter(recruiter_id)
    return [JobResponse.from_stored(stored) for stored in stored_jobs]
