"""Shared test fixtures. All tests run against the deterministic fake LLM client."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_llm_client
from app.core.security import hash_password
from app.llm.fake_client import FakeLLMClient
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"


#: The recruiter account every test signs in as. The password exists only here, in the test
#: suite, and is hashed at import time - nothing in the application's own configuration or
#: source carries a recruiter password, in plaintext or otherwise.
TEST_RECRUITER_EMAIL = "recruiter@intermind.test"
TEST_RECRUITER_PASSWORD = "test-recruiter-password"
# Hashed at the lowest scrypt cost: the suite signs in on almost every test, and the
# production cost (~0.5s per verification, by design) would add minutes. The verification path
# under test is identical - the cost travels inside the hash.
_TEST_RECRUITER_PASSWORD_HASH = hash_password(TEST_RECRUITER_PASSWORD, n=2**8)


def recruiter_credentials(email: str = TEST_RECRUITER_EMAIL) -> dict[str, str]:
    """The body of a valid signup or sign-in for ``email``.

    One password for every test account: the suite is not testing password strength, and a
    shared one keeps the low-cost hash (see below) in one place.
    """
    return {"email": email, "password": TEST_RECRUITER_PASSWORD}


@pytest.fixture
def app():
    application = create_app()
    application.dependency_overrides[get_llm_client] = lambda: FakeLLMClient()

    yield application
    application.dependency_overrides.clear()


async def signup(client, email: str = TEST_RECRUITER_EMAIL):
    """Register ``email`` and leave ``client`` holding that recruiter's session cookie.

    Registration is how a recruiter comes into existence now - there is no configured account to
    log in as, so every test that needs a recruiter creates one.
    """
    response = await client.post("/auth/recruiter/signup", json=recruiter_credentials(email))
    assert response.status_code == 201, f"signup failed: {response.text}"
    return response


@pytest.fixture
async def client(app):
    """An HTTP client already registered and signed in as a recruiter.

    Most existing tests act as an implicit "recruiter" (creating jobs/plans, starting
    interviews, reading reports/candidate lists) - see ``app.api.auth``. This fixture signs in
    through the real login endpoint and carries the resulting session cookie, so the whole
    suite exercises the same authentication path the product uses; there is no test-only way
    in. A recruiter session also satisfies candidate-scoped endpoints, which is why this one
    default covers the existing suite.

    Tests that exercise the boundary itself (``tests/integration/test_access_control.py``,
    ``test_recruiter_session_auth.py``) build their own unauthenticated or candidate-scoped
    clients instead.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await signup(ac)
        yield ac
