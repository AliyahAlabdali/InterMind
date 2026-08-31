"""FastAPI application factory and wiring."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.routes import health, jobs
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.observability.trace import TraceRecorder
from app.repositories.in_memory import InMemoryJobRepository


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Autonomous AI Interviewer", version="0.1.0")

    # Process-lifetime singletons. In-memory storage is intentional for Milestone 1.
    app.state.job_repository = InMemoryJobRepository()
    app.state.trace_recorder = TraceRecorder()

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(jobs.router)
    return app


app = create_app()
