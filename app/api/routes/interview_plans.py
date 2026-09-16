"""Interview plan endpoints: build and fetch the O*NET-grounded plan for a job.

Nested under ``/jobs/{job_id}`` since a plan only exists in relation to an already-analysed
job; this router does not change the behaviour of ``app.api.routes.jobs``.

Access note: like ``app.api.routes.jobs``, these endpoints are NOT covered by the Milestone 4
access boundary (see ``app.api.auth``) and are fully public. Resource-level authorization for
interview plans is Milestone 6-B productionization work - do not assume or claim these are
protected.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import (
    get_interview_plan_repository,
    get_interview_planner_service,
    get_job_repository,
)
from app.core.exceptions import InterviewPlanNotFound
from app.domain.interview_plan import InterviewPlan
from app.repositories.ports import InterviewPlanRepository, JobRepository
from app.services.interview_planner import InterviewPlannerService

router = APIRouter(tags=["interview-plans"])


@router.post("/jobs/{job_id}/interview-plan", response_model=InterviewPlan)
async def create_interview_plan(
    job_id: str,
    response: Response,
    job_repo: JobRepository = Depends(get_job_repository),
    planner: InterviewPlannerService = Depends(get_interview_planner_service),
    plan_repo: InterviewPlanRepository = Depends(get_interview_plan_repository),
) -> InterviewPlan:
    """Create the interview plan for ``job_id``, or return it if it already exists.

    Idempotent by design: a plan a later stateful interview loop (Milestone 4) may already
    be referencing should never be silently regenerated (new question ids, reshuffled
    selection, ...) just because this endpoint was called again. Returns 201 only the first
    time a plan is actually created; a repeat call returns the existing plan with 200.
    """
    stored_job = await job_repo.get(job_id)  # raises JobNotFound -> 404

    try:
        existing_plan = await plan_repo.get(job_id)
    except InterviewPlanNotFound:
        pass
    else:
        response.status_code = status.HTTP_200_OK
        return existing_plan

    plan = await planner.plan(job_id, stored_job.job_spec)
    response.status_code = status.HTTP_201_CREATED
    return await plan_repo.add(plan)


@router.get("/jobs/{job_id}/interview-plan", response_model=InterviewPlan)
async def get_interview_plan(
    job_id: str,
    plan_repo: InterviewPlanRepository = Depends(get_interview_plan_repository),
) -> InterviewPlan:
    return await plan_repo.get(job_id)  # raises InterviewPlanNotFound -> 404
