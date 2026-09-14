"""Maps domain exceptions to HTTP responses."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    ConfigurationError,
    DomainError,
    InterviewAlreadyCompleted,
    InterviewNotCompleted,
    InterviewNotFound,
    InterviewPlanNotFound,
    InterviewStateUnavailable,
    JobNotFound,
    LLMError,
    OccupationNotFound,
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

    @app.exception_handler(DomainError)
    async def _handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _handle_value_error(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
