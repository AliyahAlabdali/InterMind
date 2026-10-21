"""Durable auth and admission tests using only the disposable local PostgreSQL cluster."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.deps import get_llm_client
from app.api.recruiter_session import SqlRecruiterSessionStore
from app.core.config import Settings, get_settings
from app.core.exceptions import RecruiterEmailTaken
from app.core.limits import LIMITS, Limit
from app.core.rate_limit import RateLimitExceeded
from app.core.sql_rate_limit import SqlRateLimiter
from app.db.models import RateLimitEventRow, RecruiterRow, RecruiterSessionRow
from app.domain.job import JobSpec
from app.domain.recruiter import Recruiter
from app.llm.fake_client import FakeLLMClient
from app.repositories.ports import StoredJob
from app.repositories.sql import SqlJobRepository

pytest_plugins = ("tests.integration.test_durable_interview_postgres",)


async def test_session_hash_expiry_revocation_and_restart(sql_engine):
    sessions = async_sessionmaker(sql_engine, expire_on_commit=False)
    # The existing fixture inserts a durable legacy recruiter account.
    first = SqlRecruiterSessionStore(sessions, ttl_seconds=3600)
    issued = await first.create("legacy")
    assert issued.token != hashlib.sha256(issued.token.encode()).hexdigest()
    async with sessions() as db:
        row = await db.get(RecruiterSessionRow, hashlib.sha256(issued.token.encode()).hexdigest())
        assert row is not None and row.token_hash != issued.token
    restarted = SqlRecruiterSessionStore(sessions, ttl_seconds=3600)
    assert (await restarted.resolve(issued.token)).recruiter_id == "legacy"
    await restarted.revoke(issued.token)
    assert await first.resolve(issued.token) is None
    expiring = await first.create("legacy")
    async with sessions.begin() as db:
        await db.execute(update(RecruiterSessionRow).where(
            RecruiterSessionRow.token_hash == hashlib.sha256(expiring.token.encode()).hexdigest()
        ).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    assert await restarted.resolve(expiring.token) is None


async def test_duplicate_signup_rolls_back_its_session(sql_engine):
    sessions = async_sessionmaker(sql_engine, expire_on_commit=False)
    store = SqlRecruiterSessionStore(sessions, ttl_seconds=3600)
    with pytest.raises(RecruiterEmailTaken):
        await store.create_with_recruiter(
            Recruiter(email="legacy@intermind.test", password_hash="unused-test-hash")
        )
    async with sessions() as db:
        assert (await db.scalar(select(func.count()).select_from(RecruiterRow))) == 1
        assert (await db.scalar(select(func.count()).select_from(RecruiterSessionRow))) == 0


async def test_rate_limits_are_atomic_across_instances_and_restart(sql_engine, monkeypatch):
    monkeypatch.setitem(LIMITS, "test_actor", (Limit(2, 60),))
    monkeypatch.setitem(LIMITS, "test_global", (Limit(3, 60),))
    sessions = async_sessionmaker(sql_engine, expire_on_commit=False)
    now = datetime.now(UTC)
    first = SqlRateLimiter(sessions, clock=lambda: now)
    second = SqlRateLimiter(sessions, clock=lambda: now)

    async def attempt(limiter):
        try:
            await limiter.check(("test_actor", "one"), ("test_global", "all"))
            return True
        except RateLimitExceeded:
            return False

    admitted = await asyncio.gather(*(attempt(first if i % 2 else second) for i in range(4)))
    assert sum(admitted) == 2
    # A refused actor attempt must not spend the shared global budget.
    await second.check(("test_actor", "two"), ("test_global", "all"))
    with pytest.raises(RateLimitExceeded):
        await first.check(("test_actor", "three"), ("test_global", "all"))
    async with sessions() as db:
        rows = (await db.execute(select(RateLimitEventRow))).scalars().all()
    assert len(rows) == 6  # two named budgets per admitted request
    later = SqlRateLimiter(sessions, clock=lambda: now + timedelta(seconds=61))
    await later.check(("test_actor", "one"), ("test_global", "all"))


async def test_database_failure_never_admits():
    class BrokenSessions:
        def begin(self):
            raise OSError("database unavailable")

    with pytest.raises(OSError):
        await SqlRateLimiter(BrokenSessions()).check(("login_global", "all"))
    with pytest.raises(OSError):
        await SqlRecruiterSessionStore(BrokenSessions(), ttl_seconds=3600).create("legacy")


async def test_recruiter_cookie_survives_app_restart_and_ownership_stays_scoped(
    sql_engine, isolated_postgres, monkeypatch,
):
    main = importlib.import_module("app.main")
    settings = Settings(
        _env_file=None, database_url=isolated_postgres, require_database=True,
        shared_state_backend="postgres", recruiter_session_cookie_secure=True,
        llm_provider="fake", speech_provider="browser",
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)

    def new_app():
        app = main.create_app()
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient()
        return app

    first = new_app()
    async with AsyncClient(transport=ASGITransport(app=first), base_url="https://test") as client:
        response = await client.post("/auth/recruiter/signup", json={
            "email": "first@intermind.test", "password": "long-test-password"
        })
        assert response.status_code == 201
        assert "secure" in response.headers["set-cookie"].lower()
        assert "httponly" in response.headers["set-cookie"].lower()
        assert "samesite=strict" in response.headers["set-cookie"].lower()
        token = client.cookies.get("intermind_recruiter_session")
    await first.state.db_engine.dispose()

    restarted = new_app()
    async with AsyncClient(
        transport=ASGITransport(app=restarted), base_url="https://test"
    ) as client:
        client.cookies.set("intermind_recruiter_session", token)
        assert (await client.get("/auth/recruiter/session")).json()["authenticated"] is True
        recruiter_id = (await restarted.state.recruiter_session_store.resolve(token)).recruiter_id
        sessions = async_sessionmaker(sql_engine, expire_on_commit=False)
        await SqlJobRepository(sessions).add(StoredJob(
            recruiter_id=recruiter_id, job_description="A job",
            job_spec=JobSpec(role_title="Engineer"),
        ))
        assert len((await client.get("/jobs")).json()) == 1
        async with AsyncClient(
            transport=ASGITransport(app=restarted), base_url="https://test"
        ) as other:
            created = await other.post("/auth/recruiter/signup", json={
                "email": "second@intermind.test", "password": "another-long-test-password"
            })
            assert created.status_code == 201
            assert (await other.get("/jobs")).json() == []
        await client.post("/auth/recruiter/logout")
        assert (await client.get("/auth/recruiter/session")).json()["authenticated"] is False
        assert (await client.get("/jobs")).status_code == 401
    await restarted.state.db_engine.dispose()
