"""Speech authorization endpoint for the candidate's browser.

Scoped to an interview on purpose. A bare ``/speech/token`` would have needed its own auth
scheme; hanging it off ``/interviews/{interview_id}`` lets it reuse ``require_candidate_access``
unchanged, so exactly the people who may take an interview may mint a speech token for it - a
candidate token for interview A cannot mint one while pretending to be interview B, and a
recruiter credential works here for the same reason it works on the other candidate endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth import require_candidate_access
from app.api.deps import get_speech_token_service
from app.core.config import Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.services.speech_token import SpeechToken, SpeechTokenService

router = APIRouter(tags=["speech"])


@router.get(
    "/interviews/{interview_id}/speech-token",
    response_model=SpeechToken,
    dependencies=[Depends(require_candidate_access)],
)
async def issue_speech_token(
    interview_id: str,
    settings: Settings = Depends(get_settings),
    service: SpeechTokenService = Depends(get_speech_token_service),
) -> SpeechToken:
    """Return a short-lived Azure Speech authorization token for this interview's candidate.

    Never returns the Speech resource key - only a token that expires in minutes (see
    ``app.services.speech_token``). 503 when the speech service itself is unreachable, so the
    candidate UI can fall back to typing without treating it as a broken interview.
    """
    # `interview_id` is consumed by require_candidate_access (FastAPI binds the path parameter
    # into the dependency), which is what scopes this endpoint to one interview.
    del interview_id

    if settings.speech_provider != "azure":
        raise ConfigurationError(
            f"Speech tokens requested but SPEECH_PROVIDER is '{settings.speech_provider}'"
        )

    return await service.issue()
