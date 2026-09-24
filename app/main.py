"""FastAPI application factory and wiring."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.recruiter_session import RecruiterSessionStore
from app.api.routes import (
    activity,
    auth,
    health,
    interview_plans,
    interviews,
    jobs,
    speech,
)
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.engine import create_engine, create_session_factory
from app.observability.trace import TraceRecorder
from app.repositories.in_memory import (
    InMemoryActivityRepository,
    InMemoryCandidateRepository,
    InMemoryInterviewPlanRepository,
    InMemoryInterviewReportRepository,
    InMemoryInterviewSessionRepository,
    InMemoryJobRepository,
    InMemoryRecruiterRepository,
)
from app.repositories.sql import (
    SqlActivityRepository,
    SqlCandidateRepository,
    SqlInterviewPlanRepository,
    SqlInterviewReportRepository,
    SqlInterviewSessionRepository,
    SqlJobRepository,
    SqlRecruiterRepository,
)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        yield
        # Return pooled connections on shutdown rather than leaving the process to drop them.
        engine = getattr(application.state, "db_engine", None)
        if engine is not None:
            await engine.dispose()

    app = FastAPI(title="Autonomous AI Interviewer", version="0.1.0", lifespan=lifespan)

    # Explicit origins from configuration, never a wildcard - see Settings.allowed_origins.
    # In production the app is same-origin with its API (Vercel rewrites /api to this backend),
    # so this is not on the browser's path at all; it exists for direct API access.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.trace_recorder = TraceRecorder()
    # Recruiter browser sessions. In-memory by design for this milestone: a restart signs every
    # recruiter out, but their *account* and everything they own is in PostgreSQL and survives.
    # See docs/recruiter-auth.md.
    app.state.recruiter_session_store = RecruiterSessionStore(
        ttl_seconds=settings.recruiter_session_ttl_seconds
    )
    # app.state.onet_kb and app.state.interview_graph are set lazily on first use - see
    # app.api.deps.get_onet_kb and app.api.deps.get_interview_graph.

    # Repositories. With DATABASE_URL set the product is genuinely persistent: recruiter
    # accounts and everything they own survive a restart. Without it the in-memory
    # implementations are used, which is what the test suite runs on and what a contributor
    # gets with no database - correct for development, never correct for a deployment, so it
    # says so at startup.
    if settings.database_url:
        engine = create_engine(settings.database_url, echo=settings.database_echo)
        sessions = create_session_factory(engine)
        app.state.db_engine = engine
        app.state.recruiter_repository = SqlRecruiterRepository(sessions)
        app.state.job_repository = SqlJobRepository(sessions)
        app.state.interview_plan_repository = SqlInterviewPlanRepository(sessions)
        app.state.interview_session_repository = SqlInterviewSessionRepository(sessions)
        app.state.interview_report_repository = SqlInterviewReportRepository(sessions)
        app.state.candidate_repository = SqlCandidateRepository(sessions)
        app.state.activity_repository = SqlActivityRepository(sessions)
    else:
        logging.getLogger(__name__).warning(
            "DATABASE_URL is not set - running with in-memory storage. Recruiter accounts, "
            "jobs, interviews and reports will be lost when this process stops. Do not deploy "
            "in this mode; see docs/deployment.md."
        )
        app.state.db_engine = None
        _wire_in_memory(app)

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(jobs.router)
    app.include_router(interview_plans.router)
    app.include_router(interviews.router)
    app.include_router(activity.router)
    app.include_router(speech.router)

    return app


def _wire_in_memory(app: FastAPI) -> None:
    """Development/test storage. Nothing here survives the process."""
    app.state.recruiter_repository = InMemoryRecruiterRepository()
    app.state.job_repository = InMemoryJobRepository()
    app.state.interview_plan_repository = InMemoryInterviewPlanRepository()
    app.state.interview_session_repository = InMemoryInterviewSessionRepository(
        app.state.job_repository
    )
    app.state.interview_report_repository = InMemoryInterviewReportRepository()
    app.state.candidate_repository = InMemoryCandidateRepository()
    app.state.activity_repository = InMemoryActivityRepository(app.state.job_repository)



app = create_app()
