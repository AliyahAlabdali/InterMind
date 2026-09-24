"""Interview plan endpoints: build and fetch the O*NET-grounded plan for a job.

Nested under ``/jobs/{job_id}`` since a plan only exists in relation to an already-analysed job;
this router does not change the behaviour of ``app.api.routes.jobs``.

**Access.** Both endpoints are recruiter-owner scoped, through the same
:func:`~app.api.auth.current_recruiter_id` and ``get_for_recruiter`` pair every other
recruiter-owned route uses. They were public until this change, which was correct when the
product had a single configured recruiter and became a cross-tenant hole when it grew accounts:
a job id alone was enough to read another recruiter's assessment strategy, and to generate a
plan on their job.

The one exception is deliberate and narrow. A candidate part way through an interview for this
job may ``GET`` the plan with their own interview's access token, and receives
:class:`~app.api.schemas.CandidateInterviewPlanResponse` - the role name and the bare target
list their screen needs - never the plan itself. See
:func:`~app.api.auth.require_interview_plan_access`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.api.auth import PlanAudience, current_recruiter_id, require_interview_plan_access
from app.api.deps import (
    get_interview_plan_repository,
    get_interview_planner_service,
    get_job_repository,
)
from app.api.schemas import CandidateInterviewPlanResponse
from app.core.exceptions import InterviewPlanNotFound
from app.domain.interview_plan import InterviewPlan
from app.repositories.ports import InterviewPlanRepository, JobRepository
from app.services.interview_planner import InterviewPlannerService

router = APIRouter(tags=["interview-plans"])


@router.post("/jobs/{job_id}/interview-plan", response_model=InterviewPlan)
async def create_interview_plan(
    job_id: str,
    response: Response,
    recruiter_id: str = Depends(current_recruiter_id),
    job_repo: JobRepository = Depends(get_job_repository),
    planner: InterviewPlannerService = Depends(get_interview_planner_service),
    plan_repo: InterviewPlanRepository = Depends(get_interview_plan_repository),
) -> InterviewPlan:
    """Create the interview plan for ``job_id``, or return it if it already exists.

    Recruiter-only, and only for a job this recruiter owns: planning runs the O*NET match and
    question-generation pipeline against someone's job, so leaving it open let an anonymous
    caller both spend that work and create state on another tenant's resource.

    Idempotent by design: a plan the stateful interview loop may already be referencing should
    never be silently regenerated (new question ids, reshuffled selection, ...) just because
    this endpoint was called again. Returns 201 only the first time a plan is actually created;
    a repeat call returns the existing plan with 200.
    """
    # Ownership first, and through the owner-scoped query rather than a fetch-then-compare:
    # another recruiter's job raises JobNotFound (404) exactly as an unknown id does.
    stored_job = await job_repo.get_for_recruiter(job_id, recruiter_id)

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


@router.get("/jobs/{job_id}/interview-plan", response_model=None)
async def get_interview_plan(
    job_id: str,
    audience: PlanAudience = Depends(require_interview_plan_access),
    plan_repo: InterviewPlanRepository = Depends(get_interview_plan_repository),
) -> InterviewPlan | CandidateInterviewPlanResponse:
    """Return the interview plan for ``job_id``.

    The owning recruiter gets the whole plan. A candidate interviewing for this job gets the
    reduced candidate shape; the authorization and the shape are decided together in
    :func:`~app.api.auth.require_interview_plan_access`, so there is no path that authorizes a
    candidate and then returns the recruiter's view by accident.
    """
    plan = await plan_repo.get(job_id)  # raises InterviewPlanNotFound -> 404
    if audience is PlanAudience.CANDIDATE:
        return CandidateInterviewPlanResponse.from_plan(plan)
    return plan
