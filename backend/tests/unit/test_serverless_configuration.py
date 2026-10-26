"""No network or cloud calls: timeout and pool configuration regressions."""

from __future__ import annotations

import asyncio
import importlib
import ssl
import types

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.exceptions import ConfigurationError, LLMError
from app.core.request_budget import RequestDeadlineMiddleware
from app.db.engine import create_engine, verified_tls_connect_args
from app.domain.job import JobSpec
from app.llm.openai_client import OpenAIStructuredClient


async def test_openai_timeout_cancels_a_stalled_call_without_a_paid_api():
    async def parse(**_):
        await asyncio.sleep(1)

    client = OpenAIStructuredClient(
        api_key="test-only", model="gpt-4o-mini", timeout_seconds=0.01, max_retries=0
    )
    assert client._client.max_retries == 0
    assert client._client.timeout.connect == 0.01
    assert client._client.timeout.read == 0.01
    client._client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(parse=parse))
    )
    with pytest.raises(LLMError):
        await client.generate_structured(prompt="p", input_text="t", schema=JobSpec)


def test_openai_timeout_keeps_the_sdk_fast_connect_limit():
    client = OpenAIStructuredClient(api_key="test-only", model="gpt-4o-mini")
    assert client._client.timeout.connect == 5.0
    assert client._client.timeout.read == 600.0


async def test_openai_does_not_start_when_request_budget_is_spent(monkeypatch):
    calls = 0

    async def parse(**_):
        nonlocal calls
        calls += 1

    monkeypatch.setattr("app.llm.openai_client.seconds_remaining", lambda: 9)
    client = OpenAIStructuredClient(api_key="test-only", model="gpt-4o-mini")
    client._client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(parse=parse))
    )
    with pytest.raises(LLMError):
        await client.generate_structured(prompt="p", input_text="t", schema=JobSpec)
    assert calls == 0


async def test_request_deadline_returns_504():
    app = FastAPI()

    @app.get("/slow")
    async def slow():
        await asyncio.sleep(1)
        return {"unexpected": True}

    app.add_middleware(RequestDeadlineMiddleware, seconds=0.01)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/slow")
    assert response.status_code == 504


async def test_pool_modes_are_opt_in_and_do_not_connect():
    url = "postgresql+asyncpg://test@127.0.0.1:1/unused"
    default = create_engine(url)
    small = create_engine(url, pool_mode="small", pool_size=1, max_overflow=0)
    null = create_engine(url, pool_mode="null")
    try:
        assert default.pool.size() == 5
        assert small.pool.size() == 1
        assert isinstance(null.pool, NullPool)
    finally:
        await default.dispose()
        await small.dispose()
        await null.dispose()


def test_shared_state_refuses_missing_database(monkeypatch):
    main = importlib.import_module("app.main")
    settings = Settings(_env_file=None, database_url=None, shared_state_backend="postgres")
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    with pytest.raises(ConfigurationError):
        main.create_app()


def test_null_pool_uses_unique_prepared_statement_names(monkeypatch):
    captured = {}

    def fake_create_async_engine(_url, **options):
        captured.update(options)

    monkeypatch.setattr("app.db.engine.create_async_engine", fake_create_async_engine)
    create_engine("postgresql+asyncpg://test@127.0.0.1:1/unused", pool_mode="null")
    name = captured["connect_args"]["prepared_statement_name_func"]
    assert name().startswith("__intermind_")
    assert name() != name()


def test_verified_tls_is_opt_in_and_preserves_null_pool_options(monkeypatch):
    captured = {}

    def fake_create_async_engine(url, **options):
        captured.update(url=url, options=options)

    monkeypatch.setattr("app.db.engine.create_async_engine", fake_create_async_engine)
    azure_url = "postgresql+asyncpg://test:synthetic@db.example.invalid/unused?ssl=require"
    monkeypatch.delenv("DATABASE_SSL_VERIFY_FULL", raising=False)
    assert Settings(_env_file=None).database_ssl_verify_full is False
    monkeypatch.setenv("DATABASE_SSL_VERIFY_FULL", "true")
    assert Settings(_env_file=None).database_ssl_verify_full is True
    create_engine(azure_url)
    assert captured["url"] == azure_url
    assert "connect_args" not in captured["options"]

    captured.clear()
    url = "postgresql+asyncpg://test:synthetic@db.example.invalid/unused"
    create_engine(url, pool_mode="null", ssl_verify_full=True)
    args = captured["options"]["connect_args"]
    assert isinstance(args["ssl"], ssl.SSLContext)
    assert args["ssl"].check_hostname is True
    assert args["ssl"].verify_mode == ssl.CERT_REQUIRED
    assert args["prepared_statement_name_func"]() != args["prepared_statement_name_func"]()


def test_application_passes_tls_opt_in_to_engine(monkeypatch):
    main = importlib.import_module("app.main")
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://test:synthetic@db.example.invalid/unused",
        database_ssl_verify_full=True,
    )
    captured = {}
    real_create_engine = main.create_engine

    def capture_create_engine(url, **options):
        captured.update(options)
        return real_create_engine(url, **options)

    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "create_engine", capture_create_engine)
    app = main.create_app()
    assert captured["ssl_verify_full"] is True
    assert app.state.db_engine is not None


@pytest.mark.parametrize(
    "parameter", ["ssl=verify-full", "sslmode=require", "channel_binding=require"]
)
def test_verified_tls_rejects_conflicting_url_options_without_leaking_secrets(parameter):
    url = f"postgresql+asyncpg://test:synthetic-secret@db.example.invalid/unused?{parameter}"
    with pytest.raises(ValueError, match="DATABASE_SSL_VERIFY_FULL") as error:
        verified_tls_connect_args(url, verify_full=True)
    assert "synthetic-secret" not in str(error.value)
    assert verified_tls_connect_args(url, verify_full=False) == {}


def test_verified_tls_invalid_url_error_does_not_include_credentials():
    with pytest.raises(ValueError, match="invalid DATABASE_URL") as error:
        verified_tls_connect_args("not-a-url-synthetic-secret", verify_full=True)
    assert "synthetic-secret" not in str(error.value)
