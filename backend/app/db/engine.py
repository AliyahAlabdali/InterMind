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
import ssl
from uuid import uuid4

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

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


def verified_tls_connect_args(url: str, *, verify_full: bool) -> dict:
    """Opt in to system-CA and hostname-verified TLS for asyncpg connections."""
    if not verify_full:
        return {}
    # A copied provider URL may include sslmode/ssl settings that conflict with the explicit
    # context. Reject them without ever including the URL or its credentials in the error.
    try:
        query = make_url(normalize_database_url(url)).query
    except (ArgumentError, ValueError):
        raise ValueError("invalid DATABASE_URL for verified TLS") from None
    if {"ssl", "sslmode", "sslrootcert", "channel_binding"} & {
        key.lower() for key in query
    }:
        raise ValueError(
            "DATABASE_SSL_VERIFY_FULL requires DATABASE_URL without TLS query parameters"
        )
    return {"ssl": ssl.create_default_context(ssl.Purpose.SERVER_AUTH)}


def create_engine(
    url: str, *, echo: bool = False, pool_mode: str = "default",
    pool_size: int = 2, max_overflow: int = 0, ssl_verify_full: bool = False,
) -> AsyncEngine:
    """Build the process-wide async engine.

    ``pool_pre_ping`` because managed PostgreSQL (Azure included) drops idle connections behind
    the pool's back; without it the first request after an idle period fails on a dead socket
    instead of transparently reconnecting.
    """
    options: dict = {"echo": echo, "pool_pre_ping": True}
    if pool_mode == "null":
        options["poolclass"] = NullPool
        # Transaction poolers can hand the same server connection to another function. Avoid
        # asyncpg's sequential prepared-statement names colliding across those clients.
        options["connect_args"] = {
            "prepared_statement_name_func": lambda: f"__intermind_{uuid4()}__"
        }
    elif pool_mode == "small":
        if pool_size < 1 or max_overflow < 0:
            raise ValueError("database pool size must be positive and overflow nonnegative")
        options.update(pool_size=pool_size, max_overflow=max_overflow, pool_timeout=5)
    elif pool_mode != "default":
        raise ValueError("unknown database pool mode")
    tls_args = verified_tls_connect_args(url, verify_full=ssl_verify_full)
    if tls_args:
        options.setdefault("connect_args", {}).update(tls_args)
    return create_async_engine(normalize_database_url(url), **options)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    """Session factory for repositories.

    ``expire_on_commit=False`` so a returned row stays readable after its transaction commits -
    repositories convert rows to Pydantic domain models, and re-fetching attributes after commit
    would mean a second round trip for data already in hand.
    """
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
