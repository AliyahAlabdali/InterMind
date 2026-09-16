"""Interview endpoints: start an interview from an existing plan, submit answers, poll status.

Thin HTTP wrapper around :class:`app.services.interview_session.InterviewSessionService`,
which drives the LangGraph interview loop in :mod:`app.agents.interview_graph`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.auth import require_candidate_access, require_recruiter_access
from app.api.deps import (
    get_candidate_repository,
    get_interview_plan_repository,
    get_interview_report_repository,
    get_interview_session_repository,
    get_interview_session_service,
    get_report_generation_service,
)
from app.api.schemas import (
    CandidateSessionSummary,
    InterviewResponse,
    StartInterviewRequest,
    SubmitAnswerRequest,
)
from app.core.exceptions import CandidateNotFound, InterviewNotCompleted, InterviewReportNotFound
from app.domain.candidate import Candidate
from app.domain.interview import InterviewStatus
from app.domain.report import InterviewReport
from app.repositories.ports import (
    CandidateRepository,
    InterviewPlanRepository,
    InterviewReportRepository,
    InterviewSessionRepository,
)
from app.services.interview_session import InterviewSessionService
from app.services.report_generation import ReportGenerationService

router = APIRouter(tags=["interviews"])

_UNKNOWN_CANDIDATE = Candidate(id="", name="Unknown Candidate", email="")


async def _get_candidate_for_session(
    session_repo: InterviewSessionRepository,
    candidate_repo: CandidateRepository,
    interview_id: str,
) -> Candidate:
    """Resolve the candidate for an interview session.

    Falls back to a placeholder rather than raising for a session with no/an unknown
    ``candidate_id`` (legacy or test-constructed sessions - see ``InterviewSession.
    candidate_id``'s default) - a missing candidate record must never break reading an
    otherwise-valid interview's state.
    """
    session = await session_repo.get(interview_id)
    if not session.candidate_id:
        return _UNKNOWN_CANDIDATE
    try:
        return await candidate_repo.get(session.candidate_id)
    except CandidateNotFound:
        return _UNKNOWN_CANDIDATE


async def _get_or_generate_report(
    *,
    interview_id: str,
    session_service: InterviewSessionService,
    plan_repo: InterviewPlanRepository,
    report_repo: InterviewReportRepository,
    report_service: ReportGenerationService,
) -> InterviewReport:
    try:
        return await report_repo.get(interview_id)
    except InterviewReportNotFound:
        pass

    state = await session_service.get_state(interview_id)
    plan = await plan_repo.get(state.job_id)
    report = await report_service.generate(interview_id=interview_id, plan=plan, state=state)
    return await report_repo.add(report)


@router.post(
    "/interviews",
    response_model=InterviewResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recruiter_access)],
)
async def start_interview(
    payload: StartInterviewRequest,
    service: InterviewSessionService = Depends(get_interview_session_service),
    session_repo: InterviewSessionRepository = Depends(get_interview_session_repository),
) -> InterviewResponse:
    """Start a new interview thread from ``job_id``'s existing interview plan, for the named
    candidate.

    Recruiter-only (see ``app.api.auth``) - this is what mints the interview's own access
    token, so only a recruiter credential may create new sessions/tokens. Raises 404 (via
    ``InterviewPlanNotFound``) if no plan exists yet for that job.
    """
    interview_id, state = await service.start(
        payload.job_id, payload.candidate_name, payload.candidate_email
    )
    session = await session_repo.get(interview_id)
    return InterviewResponse.from_state(
        interview_id,
        state,
        payload.candidate_name,
        payload.candidate_email,
        candidate_access_token=session.access_token,
    )


@router.post(
    "/interviews/{interview_id}/answers",
    response_model=InterviewResponse,
    dependencies=[Depends(require_candidate_access)],
)
async def submit_answer(
    interview_id: str,
    payload: SubmitAnswerRequest,
    service: InterviewSessionService = Depends(get_interview_session_service),
    session_repo: InterviewSessionRepository = Depends(get_interview_session_repository),
    candidate_repo: CandidateRepository = Depends(get_candidate_repository),
) -> InterviewResponse:
    """Submit the candidate's answer and resume the interview.

    The graph evaluates the answer and autonomously decides the next step: advance to the
    next question, ask a follow-up, or finish. Requires this interview's own access token (or
    a recruiter credential) - see ``app.api.auth``.
    """
    state = await service.submit_answer(interview_id, payload.answer)
    candidate = await _get_candidate_for_session(session_repo, candidate_repo, interview_id)
    return InterviewResponse.from_state(interview_id, state, candidate.name, candidate.email)


@router.get(
    "/interviews/{interview_id}",
    response_model=InterviewResponse,
    dependencies=[Depends(require_candidate_access)],
)
async def get_interview(
    interview_id: str,
    service: InterviewSessionService = Depends(get_interview_session_service),
    session_repo: InterviewSessionRepository = Depends(get_interview_session_repository),
    candidate_repo: CandidateRepository = Depends(get_candidate_repository),
) -> InterviewResponse:
    """Requires this interview's own access token (or a recruiter credential) - see
    ``app.api.auth``."""
    state = await service.get_state(interview_id)
    candidate = await _get_candidate_for_session(session_repo, candidate_repo, interview_id)
    return InterviewResponse.from_state(interview_id, state, candidate.name, candidate.email)


@router.get(
    "/interviews/{interview_id}/report",
    response_model=InterviewReport,
    dependencies=[Depends(require_recruiter_access)],
)
async def get_interview_report(
    interview_id: str,
    session_service: InterviewSessionService = Depends(get_interview_session_service),
    plan_repo: InterviewPlanRepository = Depends(get_interview_plan_repository),
    report_repo: InterviewReportRepository = Depends(get_interview_report_repository),
    report_service: ReportGenerationService = Depends(get_report_generation_service),
) -> InterviewReport:
    """Return the evidence-based interview report, generating and caching it on first request.

    Recruiter-only, and now actually enforced (see ``app.api.auth``), not just undiscoverable
    from the candidate-facing UI: this is the endpoint scores/evidence/weaknesses live behind,
    so a candidate token - even for this exact interview - is not accepted here.

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

    return await _get_or_generate_report(
        interview_id=interview_id,
        session_service=session_service,
        plan_repo=plan_repo,
        report_repo=report_repo,
        report_service=report_service,
    )


@router.get(
    "/jobs/{job_id}/interviews",
    response_model=list[CandidateSessionSummary],
    dependencies=[Depends(require_recruiter_access)],
)
async def list_job_interviews(
    job_id: str,
    session_repo: InterviewSessionRepository = Depends(get_interview_session_repository),
    candidate_repo: CandidateRepository = Depends(get_candidate_repository),
    session_service: InterviewSessionService = Depends(get_interview_session_service),
    plan_repo: InterviewPlanRepository = Depends(get_interview_plan_repository),
    report_repo: InterviewReportRepository = Depends(get_interview_report_repository),
    report_service: ReportGenerationService = Depends(get_report_generation_service),
) -> list[CandidateSessionSummary]:
    """List every candidate interview session for ``job_id`` - the recruiter dashboard's
    candidate table (see the recruiter-workflow architecture review).

    Recruiter-only, now enforced (see ``app.api.auth``) rather than only undiscoverable from
    the candidate-facing UI: includes ``overall_score``/``recommendation`` once a session is
    completed (generating/caching the report on first request, same idempotent pattern as
    ``GET /interviews/{id}/report``).

    Returns an empty list for a job with no interview sessions yet (not a 404): the job itself
    may exist and simply have no candidates invited so far.
    """
    sessions = await session_repo.list_by_job(job_id)
    summaries: list[CandidateSessionSummary] = []
    for session in sessions:
        candidate = await _get_candidate_for_session(session_repo, candidate_repo, session.id)
        state = await session_service.get_state(session.id)

        overall_score = None
        recommendation = None
        if state.status == InterviewStatus.COMPLETED:
            report = await _get_or_generate_report(
                interview_id=session.id,
                session_service=session_service,
                plan_repo=plan_repo,
                report_repo=report_repo,
                report_service=report_service,
            )
            overall_score = report.overall_score
            recommendation = report.recommendation

        summaries.append(
            CandidateSessionSummary(
                interview_id=session.id,
                candidate_name=candidate.name,
                candidate_email=candidate.email,
                status=state.status,
                overall_score=overall_score,
                recommendation=recommendation,
            )
        )
    return summaries
