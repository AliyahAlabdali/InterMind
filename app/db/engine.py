"""Async engine and session factory.

One engine per process, created at startup from ``DATABASE_URL`` and disposed on shutdown.
Repositories receive a session factory rather than a session, so each unit of work gets its own
short-lived transaction instead of sharing one across concurrent requests.

The application never creates tables. Schema is Alembic's job (``alembic upgrade head``) - a
``create_all`` at startup would silently diverge from migrations the moment the schema changes,
and would give every deploy a different idea of what the database looks like.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)


def normalize_database_url(url: str) -> str:
    """Return ``url`` with an async driver.

    Azure, most PaaS dashboards and ``psql`` all hand out ``postgresql://…`` or
    ``postgres://…``. SQLAlchemy needs the driver named explicitly for async, so rather than
    making every deployment remember ``+asyncpg``, it is added here. An URL that already names a
    driver is left alone.
    """
    if url.startswith("postgres://"):  # some providers still emit the legacy scheme
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Build the process-wide async engine.

    ``pool_pre_ping`` because managed PostgreSQL (Azure included) drops idle connections behind
    the pool's back; without it the first request after an idle period fails on a dead socket
    instead of transparently reconnecting.
    """
    return create_async_engine(
        normalize_database_url(url),
        echo=echo,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    """Session factory for repositories.

    ``expire_on_commit=False`` so a returned row stays readable after its transaction commits -
    repositories convert rows to Pydantic domain models, and re-fetching attributes after commit
    would mean a second round trip for data already in hand.
    """
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
