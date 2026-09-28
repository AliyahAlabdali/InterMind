"""Speech authorization endpoint for the candidate's browser.

Scoped to an interview on purpose. A bare ``/speech/token`` would have needed its own auth
scheme; hanging it off ``/interviews/{interview_id}`` lets it reuse ``require_candidate_access``
unchanged, so exactly the people who may take an interview may mint a speech token for it - a
candidate token for interview A cannot mint one while pretending to be interview B, and a
recruiter credential works here for the same reason it works on the other candidate endpoints.

Three gates, in this order, and the order is the point:

1. **Authorization** (``require_candidate_access``) - this interview's own token, or its owning
   recruiter's session. Unchanged.
2. **Still needed** - a completed interview accepts no further answers, so it has no use for a
   microphone; issuing Azure credentials for one spends a real resource on a session that
   cannot use it. 409, the same status ``POST .../answers`` already returns for a finished
   interview.
3. **Budget** - per interview, and only once the first two have passed, so credential issuance
   cannot be driven by an unauthorized caller or for a dead interview.

What never leaves the backend is the Azure Speech resource key: this returns a short-lived
authorization token minted from it. See ``app.services.speech_token``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from app.api.abuse import limit_speech_token
from app.api.auth import require_candidate_access
from app.api.deps import get_interview_session_service, get_speech_token_service
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ConfigurationError,
    InterviewAlreadyCompleted,
    InterviewStateUnavailable,
)
from app.domain.interview import InterviewStatus
from app.services.interview_session import InterviewSessionService
from app.services.speech_token import SpeechToken, SpeechTokenService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["speech"])


@router.get(
    "/interviews/{interview_id}/speech-token",
    response_model=SpeechToken,
    dependencies=[Depends(require_candidate_access)],
)
async def issue_speech_token(
    interview_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    service: SpeechTokenService = Depends(get_speech_token_service),
    sessions: InterviewSessionService = Depends(get_interview_session_service),
) -> SpeechToken:
    """Return a short-lived Azure Speech authorization token for this interview's candidate.

    Never returns the Speech resource key - only a token that expires in minutes (see
    ``app.services.speech_token``). 503 when the speech service itself is unreachable, so the
    candidate UI can fall back to typing without treating it as a broken interview; 409 once
    the interview has completed and voice input is no longer needed.
    """
    # `interview_id` is also consumed by require_candidate_access (FastAPI binds the path
    # parameter into the dependency), which is what scopes this endpoint to one interview.
    if settings.speech_provider != "azure":
        raise ConfigurationError(
            f"Speech tokens requested but SPEECH_PROVIDER is '{settings.speech_provider}'"
        )

    await _reject_if_completed(sessions, interview_id)
    limit_speech_token(request, interview_id)

    return await service.issue()


async def _reject_if_completed(
    sessions: InterviewSessionService, interview_id: str
) -> None:
    """Raise :class:`InterviewAlreadyCompleted` (409) for an interview that is already over.

    An interview whose live state is unavailable is *not* rejected here. That state is the
    LangGraph checkpoint, which is in-memory and therefore gone after a restart (see
    ``app.api.deps.get_interview_graph``), and this endpoint has never consulted it before - so
    treating "I cannot tell" as "completed" would newly break voice input for an interview that
    is merely running on a restarted process. Such an interview cannot submit answers either,
    and issuance stays bounded by the per-interview budget, so allowing it costs at most a
    handful of short-lived tokens.
    """
    try:
        state = await sessions.get_state(interview_id)
    except InterviewStateUnavailable:
        logger.info(
            "speech_token_state_unavailable interview_id=%s - issuing without a status check",
            interview_id,
        )
        return
    if state.status == InterviewStatus.COMPLETED:
        raise InterviewAlreadyCompleted(interview_id)
