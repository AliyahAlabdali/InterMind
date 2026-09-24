"""Interview endpoints: start an interview from an existing plan, submit answers, poll status.

Thin HTTP wrapper around :class:`app.services.interview_session.InterviewSessionService`,
which drives the LangGraph interview loop in :mod:`app.agents.interview_graph`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status

from app.api.auth import current_recruiter_id, require_candidate_access
from app.api.deps import (
    get_activity_repository,
    get_candidate_repository,
    get_interview_plan_repository,
    get_interview_report_repository,
    get_interview_session_repository,
    get_interview_session_service,
    get_job_repository,
    get_report_generation_service,
)
from app.api.schemas import (
    CandidateSessionSummary,
    InterviewResponse,
    StartInterviewRequest,
    SubmitAnswerRequest,
)
from app.core.exceptions import (
    CandidateNotFound,
    InterviewNotCompleted,
    InterviewPlanNotFound,
    InterviewReportNotFound,
    InterviewStateUnavailable,
)
from app.domain.activity import ActivityEvent, ActivityType
from app.domain.candidate import Candidate
from app.domain.interview import InterviewState, InterviewStatus
from app.domain.report import InterviewReport
from app.repositories.ports import (
    ActivityRepository,
    CandidateRepository,
    InterviewPlanRepository,
    InterviewReportRepository,
    InterviewSessionRepository,
    JobRepository,
)
from app.services.interview_session import InterviewSessionService
from app.services.report_generation import ReportGenerationService

logger = logging.getLogger(__name__)

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


def _turns_from_this_submission(history: list[dict], answer: str) -> list[dict]:
    """The history entries produced by the answer just submitted.

    The graph appends the answered turn first, then any cross-target evidence entries resolved
    from that same answer (see ``resolve_cross_target_evidence``) - so scanning back to the
    entry carrying this answer text and taking everything from there captures exactly this
    submission's turns, and nothing from earlier ones. Falls back to the final entry if the
    answer text isn't found (a defensive case; it always is in practice).
    """
    for index in range(len(history) - 1, -1, -1):
        if history[index].get("answer") == answer:
            return history[index:]
    return history[-1:] if history else []


async def _target_name_for(
    plan_repo: InterviewPlanRepository, job_id: str, turn: dict
) -> str | None:
    """Resolve a turn's coverage-target name (e.g. "PostgreSQL") for display in the activity
    feed. Returns ``None`` rather than guessing when the plan or target can't be resolved -
    a nameless event is honest, an invented target name is not."""
    target_id = turn.get("root_question_id") or turn.get("question_id")
    if not target_id:
        return None
    try:
        plan = await plan_repo.get(job_id)
    except InterviewPlanNotFound:
        return None
    return next((t.target for t in plan.coverage_targets if t.id == target_id), None)


async def _record_answer_activity(
    *,
    activity_repo: ActivityRepository,
    plan_repo: InterviewPlanRepository,
    interview_id: str,
    candidate_name: str,
    answer: str,
    state: InterviewState,
) -> None:
    """Record what this answer actually caused, derived from the state the graph just produced.

    Never invents a transition: an evidence event exists only where the evaluation recorded
    real evidence, and a follow-up event only where the graph actually decided to follow up.
    Failures here are swallowed deliberately - the activity feed is a display concern, and must
    never be able to fail a candidate's answer submission.
    """
    try:
        for turn in _turns_from_this_submission(state.history, answer):
            evaluation = turn.get("evaluation") or {}
            target = await _target_name_for(plan_repo, state.job_id, turn)

            if evaluation.get("evidence"):
                await activity_repo.add(
                    ActivityEvent(
                        type=ActivityType.EVIDENCE_DETECTED,
                        interview_id=interview_id,
                        job_id=state.job_id,
                        candidate_name=candidate_name,
                        target=target,
                    )
                )
            if evaluation.get("decision") == "follow_up":
                await activity_repo.add(
                    ActivityEvent(
                        type=ActivityType.FOLLOW_UP_GENERATED,
                        interview_id=interview_id,
                        job_id=state.job_id,
                        candidate_name=candidate_name,
                        target=target,
                    )
                )

        if state.status == InterviewStatus.COMPLETED:
            await activity_repo.add(
                ActivityEvent(
                    type=ActivityType.INTERVIEW_COMPLETED,
                    interview_id=interview_id,
                    job_id=state.job_id,
                    candidate_name=candidate_name,
                )
            )
    except Exception:  # noqa: BLE001 - see docstring: never fail a submission over the feed
        logger.warning("Failed to record interview activity", exc_info=True)


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
)
async def start_interview(
    payload: StartInterviewRequest,
    recruiter_id: str = Depends(current_recruiter_id),
    job_repo: JobRepository = Depends(get_job_repository),
    service: InterviewSessionService = Depends(get_interview_session_service),
    session_repo: InterviewSessionRepository = Depends(get_interview_session_repository),
    activity_repo: ActivityRepository = Depends(get_activity_repository),
) -> InterviewResponse:
    """Start a new interview thread from ``job_id``'s existing interview plan, for the named
    candidate.

    Recruiter-only (see ``app.api.auth``) - this is what mints the interview's own access
    token, so only a recruiter credential may create new sessions/tokens. Raises 404 (via
    ``InterviewPlanNotFound``) if no plan exists yet for that job.

    The job must belong to the signed-in recruiter. Without that check, knowing another
    recruiter's job id would be enough to mint interviews against their role - and the resulting
    candidate data would land in their workspace.
    """
    await job_repo.get_for_recruiter(payload.job_id, recruiter_id)
    interview_id, state = await service.start(
        payload.job_id, payload.candidate_name, payload.candidate_email
    )
    session = await session_repo.get(interview_id)
    await activity_repo.add(
        ActivityEvent(
            type=ActivityType.INTERVIEW_STARTED,
            interview_id=interview_id,
            job_id=payload.job_id,
            candidate_name=payload.candidate_name,
        )
    )
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
    plan_repo: InterviewPlanRepository = Depends(get_interview_plan_repository),
    activity_repo: ActivityRepository = Depends(get_activity_repository),
) -> InterviewResponse:
    """Submit the candidate's answer and resume the interview.

    The graph evaluates the answer and autonomously decides the next step: advance to the
    next question, ask a follow-up, or finish. Requires this interview's own access token (or
    a recruiter credential) - see ``app.api.auth``.
    """
    state = await service.submit_answer(interview_id, payload.answer)
    candidate = await _get_candidate_for_session(session_repo, candidate_repo, interview_id)
    await _record_answer_activity(
        activity_repo=activity_repo,
        plan_repo=plan_repo,
        interview_id=interview_id,
        candidate_name=candidate.name,
        answer=payload.answer,
        state=state,
    )
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
)
async def get_interview_report(
    interview_id: str,
    recruiter_id: str = Depends(current_recruiter_id),
    session_repo: InterviewSessionRepository = Depends(get_interview_session_repository),
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
    if the checkpointed state is missing or invalid *and* no report has been stored yet.

    Idempotent: once generated, the same report is returned on every later call for this
    interview id - it is never regenerated (see ``InterviewReportRepository``).
    """
    # Ownership first, before anything is read or generated: another recruiter's interview is
    # reported as not found, exactly like an unknown id.
    await session_repo.get_for_recruiter(interview_id, recruiter_id)

    # A stored report is itself durable proof that this interview completed - one is only ever
    # written after the completion gate below. Serving it before consulting the graph is what
    # keeps a finished interview's report readable across a restart: LangGraph checkpoints to an
    # in-memory saver, so after one its `aget_state` has nothing for this thread id and the gate
    # used to raise InterviewStateUnavailable (500) even when PostgreSQL still held the report.
    try:
        return await report_repo.get(interview_id)
    except InterviewReportNotFound:
        pass

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
)
async def list_job_interviews(
    job_id: str,
    recruiter_id: str = Depends(current_recruiter_id),
    job_repo: JobRepository = Depends(get_job_repository),
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
    # Ownership first. This endpoint returns candidate names, scores and recommendations, so an
    # unscoped version would hand another recruiter's whole candidate table to anyone holding
    # their job id. A job owned by someone else reads as not found.
    await job_repo.get_for_recruiter(job_id, recruiter_id)

    sessions = await session_repo.list_by_job(job_id)
    summaries: list[CandidateSessionSummary] = []
    for session in sessions:
        candidate = await _get_candidate_for_session(session_repo, candidate_repo, session.id)

        # An interview's *record* is durable (PostgreSQL) but its live graph state is not: the
        # LangGraph checkpointer is in-memory, so a restart leaves rows whose state is gone.
        # One such session must not take down the whole candidate table - the recruiter still
        # needs to see who was invited. It is listed with its last durable status instead.
        stored_report: InterviewReport | None = None
        try:
            status = (await session_service.get_state(session.id)).status
        except InterviewStateUnavailable:
            # ...unless a report was stored for it, which only ever happens after the interview
            # completed. That row outlives the checkpoint, so it is the better answer than
            # "not started" for an interview the recruiter already has results for.
            try:
                stored_report = await report_repo.get(session.id)
            except InterviewReportNotFound:
                stored_report = None
            if stored_report is None:
                logger.info(
                    "interview_state_unavailable interview_id=%s - listing without live status",
                    session.id,
                )
                status = InterviewStatus.NOT_STARTED
            else:
                status = InterviewStatus.COMPLETED

        overall_score = None
        recommendation = None
        if stored_report is not None:
            overall_score = stored_report.overall_score
            recommendation = stored_report.recommendation
        elif status == InterviewStatus.COMPLETED:
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
                status=status,
                overall_score=overall_score,
                recommendation=recommendation,
                candidate_access_token=session.access_token,
            )
        )
    return summaries
