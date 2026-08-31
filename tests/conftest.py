"""Shared test fixtures. All tests run against the deterministic fake LLM client."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_llm_client
from app.llm.fake_client import FakeLLMClient
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def app():
    application = create_app()
    application.dependency_overrides[get_llm_client] = lambda: FakeLLMClient()
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
