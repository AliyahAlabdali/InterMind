"""Maps domain exceptions to HTTP responses."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AccessDenied,
    CandidateNotFound,
    ConfigurationError,
    DomainError,
    InterviewAlreadyCompleted,
    InterviewNotCompleted,
    InterviewNotFound,
    InterviewPlanNotFound,
    InterviewStateUnavailable,
    InvalidSignup,
    JobNotFound,
    LLMError,
    OccupationNotFound,
    RecruiterEmailTaken,
    SpeechServiceUnavailable,
)

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(JobNotFound)
    async def _handle_job_not_found(_: Request, exc: JobNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(OccupationNotFound)
    async def _handle_occupation_not_found(_: Request, exc: OccupationNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InterviewPlanNotFound)
    async def _handle_interview_plan_not_found(
        _: Request, exc: InterviewPlanNotFound
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InterviewNotFound)
    async def _handle_interview_not_found(_: Request, exc: InterviewNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InvalidSignup)
    async def _handle_invalid_signup(_: Request, exc: InvalidSignup) -> JSONResponse:
        # 422, and the actual reason: this one is safe to state plainly, because it describes
        # the submitted input rather than anything about existing accounts.
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(RecruiterEmailTaken)
    async def _handle_recruiter_email_taken(_: Request, exc: RecruiterEmailTaken) -> JSONResponse:
        # 409, and a message a person can act on. Registration inherently reveals whether an
        # address is taken - the alternative (claiming success and sending a "you already have
        # an account" email) needs mail infrastructure this product does not have, and silently
        # doing nothing would strand someone on a form that appears to work.
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(AccessDenied)
    async def _handle_access_denied(_: Request, exc: AccessDenied) -> JSONResponse:
        # One generic message regardless of the specific reason (missing header, wrong token,
        # wrong interview) - never reveal which case it was.
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid access token."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(CandidateNotFound)
    async def _handle_candidate_not_found(_: Request, exc: CandidateNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InterviewAlreadyCompleted)
    async def _handle_interview_already_completed(
        _: Request, exc: InterviewAlreadyCompleted
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(InterviewNotCompleted)
    async def _handle_interview_not_completed(
        _: Request, exc: InterviewNotCompleted
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(InterviewStateUnavailable)
    async def _handle_interview_state_unavailable(
        _: Request, exc: InterviewStateUnavailable
    ) -> JSONResponse:
        # Internal invariant violation (session repo / graph checkpointer out of sync), not a
        # client error: log the specifics, return a stable, non-revealing message.
        logger.error("Interview state unavailable: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Interview state is currently unavailable."},
        )

    @app.exception_handler(ConfigurationError)
    async def _handle_configuration_error(_: Request, exc: ConfigurationError) -> JSONResponse:
        # Operator error: log the specifics, return a stable, non-revealing message.
        logger.error("Configuration error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Service is not configured correctly."},
        )

    @app.exception_handler(LLMError)
    async def _handle_llm_error(_: Request, exc: LLMError) -> JSONResponse:
        # Never leak a raw provider/internal exception message to the client - log it with
        # full detail server-side and return a stable, generic message instead.
        logger.error("LLM request failed: %s", exc, exc_info=exc)
        return JSONResponse(
            status_code=502,
            content={"detail": "The language model provider failed to process the request."},
        )

    @app.exception_handler(SpeechServiceUnavailable)
    async def _handle_speech_unavailable(
        _: Request, exc: SpeechServiceUnavailable
    ) -> JSONResponse:
        # Same sanitisation rule as LLMError: the upstream detail can carry endpoint/key
        # information, so it is logged and never returned. The candidate UI falls back to
        # typing on a 503.
        logger.error("Speech token request failed: %s", exc, exc_info=exc)
        return JSONResponse(
            status_code=503,
            content={"detail": "Voice input is temporarily unavailable."},
        )

    @app.exception_handler(DomainError)
    async def _handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _handle_value_error(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
