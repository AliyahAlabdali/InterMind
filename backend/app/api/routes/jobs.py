"""Job endpoints: submit a job description, retrieve a stored analysis.

Access note
-----------
These endpoints are split rather than uniformly public, because the candidate interview needs
one small piece of one of them and nothing else here.

- ``POST /jobs`` and ``GET /jobs`` are **recruiter-only and owner-scoped**. Creating a job is a
  write that also spends an LLM call on job-description analysis, and listing them returns roles
  with their full description - neither has any candidate use. ``GET /jobs`` answers from
  ``list_by_recruiter``, so a recruiter sees only their own.
- ``GET /jobs/{job_id}`` stays **public by design**, and now returns only the role title (see
  :class:`~app.api.schemas.PublicJobResponse`). The candidate's interview screen reads it to
  show which role they are interviewing for, before any interview token exists; a candidate
  holds only their own interview's token, which is not a credential this route could scope
  against a job id.
- ``GET /jobs/{job_id}/detail`` is **recruiter-only and owner-scoped**, and returns the whole
  job. It exists because the recruiter workspace legitimately needs one job's full analysis by
  id, and used to get it from the public route - so minimising that route without adding this
  one would have taken the seniority and summary off the recruiter's own screens.

The boundary in ``app.api.auth`` is unchanged by this: recruiter-only operations stay
recruiter-only, and candidate access stays scoped to a candidate's own interview.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from app.api.abuse import limit_job_analysis
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
    request: Request,
    recruiter_id: str = Depends(current_recruiter_id),
    service: JDAnalysisService = Depends(get_jd_analysis_service),
    repo: JobRepository = Depends(get_job_repository),
) -> JobResponse:
    """Analyze a job description and store it against the signed-in recruiter.

    The owner comes from the session, never from the request. `AnalyzeJobRequest` has no
    `recruiter_id` field at all, so a client cannot even express the wish to create a job for
    somebody else.
    """
    # Budget charged after authentication (so it is keyed by a real account and an anonymous
    # caller cannot spend a recruiter's allowance) and before ``analyze`` (so a refused request
    # costs no LLM call). ``payload`` is already size-bounded by AnalyzeJobRequest, which
    # pydantic enforced before this function was entered.
    limit_job_analysis(request, recruiter_id)

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
    """Read one job's public shape: its role title, and nothing else.

    Deliberately unauthenticated - the candidate interview screen needs it to name the role
    being interviewed for, and a candidate holds only their own interview's token.

    Returns :class:`~app.api.schemas.PublicJobResponse`, which is a flat ``{id, role_title}``
    rather than the analysed ``JobSpec`` it used to return. See that model for what was public
    before and why. A recruiter reading their own job uses ``/jobs/{job_id}/detail`` below.
    """
    stored = await repo.get(job_id)
    return PublicJobResponse.from_stored(stored)


@router.get("/jobs/{job_id}/detail", response_model=JobResponse)
async def get_job_detail(
    job_id: str,
    recruiter_id: str = Depends(current_recruiter_id),
    repo: JobRepository = Depends(get_job_repository),
) -> JobResponse:
    """Read one job in full - raw description and analysed spec - as its owner.

    The recruiter counterpart to the public route above, and the reason minimising that route
    did not cost the workspace anything: ``InterviewDetailPage`` and ``ReportPage`` need a
    single job's seniority and summary by id, which no owner-scoped endpoint offered.

    Scoped through ``get_for_recruiter``, so another recruiter's job raises ``JobNotFound``
    (404) rather than 403 - the same convention as every other owner-scoped route here, and it
    does not confirm that the job exists.
    """
    stored = await repo.get_for_recruiter(job_id, recruiter_id)
    return JobResponse.from_stored(stored)


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
