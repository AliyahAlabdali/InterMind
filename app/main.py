"""FastAPI application factory and wiring."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.routes import health, interview_plans, interviews, jobs
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.observability.trace import TraceRecorder
from app.repositories.in_memory import (
    InMemoryInterviewPlanRepository,
    InMemoryInterviewReportRepository,
    InMemoryInterviewSessionRepository,
    InMemoryJobRepository,
)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Autonomous AI Interviewer", version="0.1.0")

    # Allow the Vite frontend dev server to call this API in local development (Milestone 6-A).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Process-lifetime singletons. In-memory storage is intentional through Milestone 3.
    app.state.job_repository = InMemoryJobRepository()
    app.state.interview_plan_repository = InMemoryInterviewPlanRepository()
    app.state.interview_session_repository = InMemoryInterviewSessionRepository()
    app.state.interview_report_repository = InMemoryInterviewReportRepository()
    app.state.trace_recorder = TraceRecorder()
    # app.state.onet_kb and app.state.interview_graph are set lazily on first use - see
    # app.api.deps.get_onet_kb and app.api.deps.get_interview_graph.

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(jobs.router)
    app.include_router(interview_plans.router)
    app.include_router(interviews.router)
    return app


app = create_app()
