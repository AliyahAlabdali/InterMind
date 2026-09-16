"""Shared test fixtures. All tests run against the deterministic fake LLM client."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_llm_client
from app.core.config import get_settings
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
    """An HTTP client carrying a valid recruiter credential by default.

    Most existing tests act as an implicit "recruiter" (creating jobs/plans, starting
    interviews, reading reports/candidate lists) - see ``app.api.auth``'s Milestone 4 access
    boundary. A recruiter credential also satisfies candidate-scoped endpoints (see
    ``require_candidate_access``), so this one default covers the whole existing suite without
    every test needing to know about tokens. Tests that specifically exercise the access
    boundary itself (``tests/integration/test_access_control.py``) build their own
    unauthenticated/candidate-scoped clients instead of using this fixture as-is.
    """
    transport = ASGITransport(app=app)
    recruiter_token = get_settings().recruiter_access_token
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {recruiter_token}"},
    ) as ac:
        yield ac
