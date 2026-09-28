"""Tests for the production guard against silently running on in-memory storage.

The failure this prevents is quiet and expensive: without `DATABASE_URL` the app starts, answers
health checks, accepts recruiter signups and conducts real interviews - and loses all of it on the
next container restart, which App Service does routinely. A warning in the log is not enough,
because nothing actually fails until the data is already gone.

So `REQUIRE_DATABASE` turns that into a refusal to start. It is opt-in, which is the other half of
the contract: a fresh clone and this test suite must keep working with no database at all.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.main import create_app


def _settings(**overrides) -> Settings:
    """Pinned explicitly - Settings reads the repository's real .env otherwise."""
    base = {
        "_env_file": None,
        "database_url": None,
        "require_database": False,
    }
    base.update(overrides)
    return Settings(**base)


def test_require_database_defaults_to_off():
    """A fresh clone with no .env must still run; the guard is opt-in for deployments."""
    assert _settings().require_database is False


def test_it_refuses_to_start_when_a_database_is_required_but_missing(monkeypatch):
    monkeypatch.setattr("app.main.get_settings", lambda: _settings(require_database=True))

    with pytest.raises(ConfigurationError):
        create_app()


def test_the_refusal_names_the_setting_and_no_value(monkeypatch):
    """Startup errors reach logs and crash dumps, so the message must stay value-free."""
    monkeypatch.setattr("app.main.get_settings", lambda: _settings(require_database=True))

    with pytest.raises(ConfigurationError) as raised:
        create_app()

    message = str(raised.value)
    assert "REQUIRE_DATABASE" in message
    assert "DATABASE_URL" in message
    # Naming the variables is help; quoting a value would be a credential in a log.
    assert "://" not in message
    assert "password" not in message.lower()


def test_in_memory_is_still_allowed_when_not_required(monkeypatch):
    """The local-development and test path, unchanged."""
    monkeypatch.setattr("app.main.get_settings", lambda: _settings())

    app = create_app()

    assert app.state.db_engine is None
    assert app.state.storage_backend == "in-memory"


def test_a_configured_database_is_reported_as_postgresql(monkeypatch):
    """No connection is made at startup, so this needs no server - only the wiring decision."""
    url = "postgresql://user:pw@example.postgres.database.azure.com:5432/intermind?ssl=require"
    monkeypatch.setattr(
        "app.main.get_settings", lambda: _settings(database_url=url, require_database=True)
    )

    app = create_app()

    assert app.state.db_engine is not None
    assert app.state.storage_backend == "postgresql"


async def test_health_reports_the_storage_backend(client):
    """The only way to confirm after a deploy that the fallback did not silently engage."""
    resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    # The suite itself runs on in-memory storage, which is exactly what should be reported.
    assert body["storage"] == "in-memory"


async def test_health_leaks_no_connection_detail(app, client):
    """`storage` is a mode name. It must never grow into a URL, host or credential."""
    app.state.storage_backend = "postgresql"

    resp = await client.get("/health")

    assert set(resp.json()) == {"status", "storage"}
    assert resp.json()["storage"] == "postgresql"
    for forbidden in ("://", "@", "password", "postgres.database.azure.com"):
        assert forbidden not in resp.text
