"""Maps domain exceptions to HTTP responses."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import ConfigurationError, DomainError, JobNotFound, LLMError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(JobNotFound)
    async def _handle_job_not_found(_: Request, exc: JobNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

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
        logger.warning("LLM error: %s", exc)
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(DomainError)
    async def _handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _handle_value_error(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
