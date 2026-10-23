"""The scheduled retention entry point stays opt-in and fails closed."""

import asyncio

import pytest
from fastapi import FastAPI, HTTPException, Request

from app.api.routes.privacy import scheduled_retention
from app.core.config import Settings


def _request(authorization: str | None = None) -> Request:
    app = FastAPI()
    app.state.db_session_factory = None
    headers = [] if authorization is None else [
        (b"authorization", authorization.encode("ascii"))
    ]
    return Request({"type": "http", "app": app, "headers": headers})


def test_retention_route_disabled_without_activation():
    with pytest.raises(HTTPException) as error:
        asyncio.run(scheduled_retention(
            _request(), Settings(_env_file=None, retention_enabled=False)
        ))
    assert error.value.status_code == 404


def test_retention_route_requires_secret_and_database():
    settings = Settings(
        _env_file=None, retention_enabled=True, cron_secret="synthetic-cron-secret"
    )
    for supplied in (None, "Bearer wrong"):
        with pytest.raises(HTTPException) as error:
            asyncio.run(scheduled_retention(_request(supplied), settings))
        assert error.value.status_code == 401
    with pytest.raises(HTTPException) as error:
        asyncio.run(scheduled_retention(_request("Bearer synthetic-cron-secret"), settings))
    assert error.value.status_code == 503
