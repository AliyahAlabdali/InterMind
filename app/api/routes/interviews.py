"""Interview endpoints: start an interview from an existing plan, submit answers, poll status.

Thin HTTP wrapper around :class:`app.services.interview_session.InterviewSessionService`,
which drives the LangGraph interview loop in :mod:`app.agents.interview_graph`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    get_interview_plan_repository,
    get_interview_report_repository,
    get_interview_session_service,
    get_report_generation_service,
)
from app.api.schemas import InterviewResponse, StartInterviewRequest, SubmitAnswerRequest
from app.core.exceptions import InterviewNotCompleted, InterviewReportNotFound
from app.domain.interview import InterviewStatus
from app.domain.report import InterviewReport
from app.repositories.ports import InterviewPlanRepository, InterviewReportRepository
from app.services.interview_session import InterviewSessionService
from app.services.report_generation import ReportGenerationService

router = APIRouter(tags=["interviews"])


@router.post("/interviews", response_model=InterviewResponse, status_code=status.HTTP_201_CREATED)
async def start_interview(
    payload: StartInterviewRequest,
    service: InterviewSessionService = Depends(get_interview_session_service),
) -> InterviewResponse:
    """Start a new interview thread from ``job_id``'s existing interview plan.

    Raises 404 (via ``InterviewPlanNotFound``) if no plan exists yet for that job.
    """
    interview_id, state = await service.start(payload.job_id)
    return InterviewResponse.from_state(interview_id, state)


@router.post("/interviews/{interview_id}/answers", response_model=InterviewResponse)
async def submit_answer(
    interview_id: str,
    payload: SubmitAnswerRequest,
    service: InterviewSessionService = Depends(get_interview_session_service),
) -> InterviewResponse:
    """Submit the candidate's answer and resume the interview.

    The graph evaluates the answer and autonomously decides the next step: advance to the
    next question, ask a follow-up, or finish.
    """
    state = await service.submit_answer(interview_id, payload.answer)
    return InterviewResponse.from_state(interview_id, state)


@router.get("/interviews/{interview_id}", response_model=InterviewResponse)
async def get_interview(
    interview_id: str,
    service: InterviewSessionService = Depends(get_interview_session_service),
) -> InterviewResponse:
    state = await service.get_state(interview_id)
    return InterviewResponse.from_state(interview_id, state)


@router.get("/interviews/{interview_id}/report", response_model=InterviewReport)
async def get_interview_report(
    interview_id: str,
    session_service: InterviewSessionService = Depends(get_interview_session_service),
    plan_repo: InterviewPlanRepository = Depends(get_interview_plan_repository),
    report_repo: InterviewReportRepository = Depends(get_interview_report_repository),
    report_service: ReportGenerationService = Depends(get_report_generation_service),
) -> InterviewReport:
    """Return the evidence-based interview report, generating and caching it on first request.

    404 (via ``InterviewNotFound``) if the interview doesn't exist, 409 (via
    ``InterviewNotCompleted``) if it hasn't finished yet, 500 (via ``InterviewStateUnavailable``)
    if the checkpointed state is missing or invalid - the same checks ``get_interview`` uses,
    reused here via ``InterviewSessionService.get_state`` rather than duplicated.

    Idempotent: once generated, the same report is returned on every later call for this
    interview id - it is never regenerated (see ``InterviewReportRepository``).
    """
    state = await session_service.get_state(interview_id)
    if state.status != InterviewStatus.COMPLETED:
        raise InterviewNotCompleted(interview_id)

    try:
        return await report_repo.get(interview_id)
    except InterviewReportNotFound:
        pass

    plan = await plan_repo.get(state.job_id)
    report = await report_service.generate(interview_id=interview_id, plan=plan, state=state)
    return await report_repo.add(report)
