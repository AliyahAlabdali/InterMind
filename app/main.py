"""FastAPI application factory and wiring."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.routes import health, interview_plans, jobs
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.observability.trace import TraceRecorder
from app.repositories.in_memory import InMemoryInterviewPlanRepository, InMemoryJobRepository


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Autonomous AI Interviewer", version="0.1.0")

    # Process-lifetime singletons. In-memory storage is intentional through Milestone 3.
    app.state.job_repository = InMemoryJobRepository()
    app.state.interview_plan_repository = InMemoryInterviewPlanRepository()
    app.state.trace_recorder = TraceRecorder()
    # app.state.onet_kb is set lazily on first use - see app.api.deps.get_onet_kb.

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(jobs.router)
    app.include_router(interview_plans.router)
    return app


app = create_app()
