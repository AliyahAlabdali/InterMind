"""Regression tests for the public-launch hardening pass.

Everything here guards a property that was actually wrong before this change, or a boundary the
change is at risk of moving by accident. Grouped by the finding each one closes:

1. the public job endpoint returned the whole analysed JobSpec;
2. nothing bounded how often the expensive, publicly reachable operations could be driven;
3. nothing bounded the size of the free text those operations feed to an LLM;
4. Speech credentials were issued for interviews that had already finished;
5. a password that failed validation was echoed back in the 422 body.

The tenant-isolation, candidate-token and role-separation properties these changes must not
weaken have their own suites (``test_tenant_isolation.py``, ``test_access_control.py``,
``test_job_access_control.py``, ``test_interview_plan_access_control.py``) and are unchanged.
"""

from __future__ import annotations

from collections import deque

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_onet_kb
from app.core.limits import LIMITS, MAX_ANSWER_CHARS, MAX_JOB_DESCRIPTION_CHARS
from app.knowledge.onet_kb import OnetKnowledgeBase
from tests.conftest import FIXTURES, answer_payload, recruiter_credentials

FIXTURE_KB_PATH = FIXTURES / "onet_kb_fixture.jsonl"

JD = "Backend Software Engineer\nPython and Git experience required. Critical thinking a must."

#: A value distinctive enough that finding it anywhere in a response body is unambiguous.
PASSWORD_CANARY = "correct-horse-battery-staple-CANARY-9f3a1c"
EMAIL = "a@intermind.test"


@pytest.fixture(autouse=True)
def _use_fixture_kb(app):
    """Keep these tests off the real 1016-occupation KB - none of them is about matching."""
    app.dependency_overrides[get_onet_kb] = lambda: OnetKnowledgeBase(path=FIXTURE_KB_PATH)


@pytest.fixture
async def anonymous(app):
    """A client holding no credential of any kind."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def _job(client: AsyncClient, jd: str = JD) -> str:
    response = await client.post("/jobs", json={"job_description": jd})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _interview(client: AsyncClient) -> tuple[str, str, str]:
    """A job with a plan and a started interview. Returns (job_id, interview_id, token)."""
    job_id = await _job(client)
    await client.post(f"/jobs/{job_id}/interview-plan")
    started = (await client.post("/interviews", json={"job_id": job_id})).json()
    return job_id, started["interview_id"], started["candidate_access_token"]


# =================================================================================================
# 1. The public job endpoint exposes the role title and nothing else
# =================================================================================================


async def test_the_public_job_endpoint_returns_only_id_and_role_title(client, anonymous):
    """The finding: this endpoint needs no credential and returned the full analysed JobSpec -
    every required and preferred skill, every competency, the seniority, the summary and every
    responsibility - to anyone holding a job id."""
    job_id = await _job(client)

    body = (await anonymous.get(f"/jobs/{job_id}")).json()

    assert set(body) == {"id", "role_title"}


async def test_no_analysed_jobspec_field_is_reachable_publicly(client, anonymous):
    """Named field by field rather than by shape, so that re-nesting the spec under any key -
    or flattening its fields alongside the title - fails this test rather than passing it."""
    job_id = await _job(client)

    public = (await anonymous.get(f"/jobs/{job_id}")).json()
    owner = (await client.get(f"/jobs/{job_id}/detail")).json()

    spec = owner["job_spec"]
    assert spec["skills"], "the fixture JD must analyse to a non-empty spec"

    for leaked in ("job_spec", "skills", "competencies", "responsibilities", "seniority",
                   "summary", "job_description", "recruiter_id", "created_at"):
        assert leaked not in public, f"{leaked!r} is reachable without a credential"


async def test_the_raw_job_description_never_appears_in_a_public_response(client, anonymous):
    """A whole-body substring check, not a key check: the JD must not reach an anonymous caller
    under any key, including one added later."""
    marker = "Kafka-and-Snowflake-PRIVATE-JD-MARKER"
    job_id = await _job(client, f"Staff Platform Engineer\n{marker}\nPython required.")

    response = await anonymous.get(f"/jobs/{job_id}")

    assert marker not in response.text


async def test_the_candidate_landing_flow_still_works_anonymously(client, anonymous):
    """The reason this endpoint is public at all: a candidate opening their link sees the role
    named, before any interview token exists. Minimising the shape must not break that."""
    job_id = await _job(client)

    response = await anonymous.get(f"/jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["role_title"] == "Backend Software Engineer"


async def test_an_unknown_job_is_still_a_404_for_an_anonymous_caller(anonymous):
    assert (await anonymous.get("/jobs/does-not-exist")).status_code == 404


# --- the owner-scoped replacement ----------------------------------------------------------------


async def test_the_owner_still_gets_the_whole_job_from_the_detail_route(client):
    """Recruiter retrieval must be preserved in full - the workspace reads seniority and
    summary for one job by id, which is why the public route could not simply lose them."""
    job_id = await _job(client)

    detail = await client.get(f"/jobs/{job_id}/detail")

    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == job_id
    assert body["job_description"] == JD
    assert body["job_spec"]["role_title"] == "Backend Software Engineer"
    assert body["job_spec"]["seniority"]


async def test_the_detail_route_refuses_an_anonymous_caller(client, anonymous):
    job_id = await _job(client)

    assert (await anonymous.get(f"/jobs/{job_id}/detail")).status_code == 401


async def test_the_detail_route_does_not_leak_across_tenants(app, client):
    """Tenant isolation on the new route, with the same 404-not-403 convention as every other
    owner-scoped route: a 403 would confirm the job exists."""
    job_id = await _job(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        await other.post(
            "/auth/recruiter/signup", json=recruiter_credentials("other@intermind.test")
        )
        response = await other.get(f"/jobs/{job_id}/detail")

    assert response.status_code == 404
    assert JD not in response.text


async def test_a_candidate_token_does_not_unlock_the_detail_route(app, client):
    """A candidate's own interview token is not a recruiter credential, here as anywhere else."""
    job_id, _, token = await _interview(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as candidate:
        response = await candidate.get(
            f"/jobs/{job_id}/detail", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 401


# =================================================================================================
# 2. Rate limiting
# =================================================================================================


def _window(bucket: str, seconds: int):
    """The configured budget for ``bucket``'s window of ``seconds``."""
    return next(limit for limit in LIMITS[bucket] if limit.seconds == seconds)


def _spend(app, bucket: str, seconds: int, count: int) -> None:
    """Pre-charge ``count`` admissions against **one specific window** of ``bucket``.

    Two reasons this writes the window's own key rather than calling ``check``:

    * ``check`` charges every window a bucket has, so filling the daily ceiling through it would
      exhaust the hourly one first and the two could never be told apart.
    * Sign-up and sign-in cost a real scrypt hash (~300ms), so draining a 50- or 100-request
      ceiling entirely over HTTP would add most of a minute to the suite and prove nothing more.

    Each test below brings a window to its edge this way and then crosses it with **real HTTP
    requests**, so what is asserted is still the route's own binding to that bucket.
    """
    limiter = app.state.rate_limiter
    limiter._events[(bucket, "all", seconds)] = deque([limiter._clock()] * count)


def _charged(app, bucket: str, seconds: int) -> int:
    """How many admissions that window has recorded."""
    return len(app.state.rate_limiter._events.get((bucket, "all", seconds), ()))


async def test_signup_is_rate_limited_deployment_wide(app, anonymous):
    """Sign-up is budgeted for the whole deployment, not per visitor.

    That is deliberate, and documented: in the deployed topology every request reaches the
    application through a proxy carrying one link-local address, so there is no per-visitor
    identity to key on (see docs/public-launch-security.md). This asserts the ceiling that does
    exist, and that it is the hourly ``signup_global`` one.
    """
    hourly = _window("signup_global", 3600)
    _spend(app, "signup_global", 3600, hourly.count - 2)

    # Real requests across the boundary: the last two admissions, then the refusal.
    for index in range(2):
        admitted = await anonymous.post(
            "/auth/recruiter/signup", json=recruiter_credentials(f"s{index}@intermind.test")
        )
        assert admitted.status_code == 201, admitted.text

    refused = await anonymous.post(
        "/auth/recruiter/signup", json=recruiter_credentials("one-too-many@intermind.test")
    )

    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) > 0


async def test_signup_has_a_separate_daily_ceiling(app, anonymous):
    """The daily window is independently binding: exhausting it refuses sign-up even with the
    hourly window untouched."""
    daily = _window("signup_global", 86400)
    _spend(app, "signup_global", 86400, daily.count)

    refused = await anonymous.post(
        "/auth/recruiter/signup", json=recruiter_credentials("daily@intermind.test")
    )

    assert refused.status_code == 429
    # The hourly window really was left alone - this is the daily ceiling doing the refusing.
    assert _charged(app, "signup_global", 3600) < _window("signup_global", 3600).count


async def test_signup_is_not_limited_per_visitor(app, anonymous):
    """The correction itself, pinned: there is no per-caller sign-up bucket any more.

    Before this, ``signup_ip`` was keyed by ``request.client.host``. In production that value is
    a single proxy address for every visitor, so the bucket throttled unrelated people against
    each other at 5/hour while presenting itself as per-visitor protection. Its absence is the
    behaviour under test - a future reintroduction must come with a verified per-visitor
    identity, not with the transport peer address.
    """
    assert "signup_ip" not in LIMITS
    assert "login_ip" not in LIMITS


async def test_login_is_rate_limited_and_stays_uniform_about_account_existence(app, anonymous):
    """The limiter must not become the account-existence oracle that the uniform login response
    exists to prevent: a registered address and an unregistered one must be refused identically,
    at the same point, with the same body."""
    await anonymous.post(
        "/auth/recruiter/signup", json=recruiter_credentials("real@intermind.test")
    )

    ten_minutes = _window("login_global", 600)
    _spend(app, "login_global", 600, ten_minutes.count)

    known = await anonymous.post(
        "/auth/recruiter/login",
        json={"email": "real@intermind.test", "password": "wrong-password"},
    )
    unknown = await anonymous.post(
        "/auth/recruiter/login",
        json={"email": "nobody@intermind.test", "password": "wrong-password"},
    )

    assert known.status_code == 429
    assert unknown.status_code == known.status_code
    assert unknown.json() == known.json()


async def test_a_successful_login_is_counted_too(app, anonymous):
    """Otherwise a valid credential would be an unlimited way to drive the session store."""
    await anonymous.post(
        "/auth/recruiter/signup", json=recruiter_credentials("real@intermind.test")
    )

    ten_minutes = _window("login_global", 600)
    _spend(app, "login_global", 600, ten_minutes.count - 1)

    admitted = await anonymous.post(
        "/auth/recruiter/login", json=recruiter_credentials("real@intermind.test")
    )
    assert admitted.status_code == 200, admitted.text

    refused = await anonymous.post(
        "/auth/recruiter/login", json=recruiter_credentials("real@intermind.test")
    )
    assert refused.status_code == 429


async def test_job_creation_is_rate_limited_per_recruiter(client):
    """The most expensive publicly reachable write: an LLM call per request."""
    budget = LIMITS["job_recruiter"][0].count
    for _ in range(budget):
        assert (await client.post("/jobs", json={"job_description": JD})).status_code == 201

    refused = await client.post("/jobs", json={"job_description": JD})

    assert refused.status_code == 429


async def test_one_recruiters_exhausted_budget_does_not_affect_another(app, client):
    """Keyed by account, so abuse by one recruiter cannot deny service to everyone else."""
    for _ in range(LIMITS["job_recruiter"][0].count):
        await client.post("/jobs", json={"job_description": JD})
    assert (await client.post("/jobs", json={"job_description": JD})).status_code == 429

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        await other.post(
            "/auth/recruiter/signup", json=recruiter_credentials("other@intermind.test")
        )
        response = await other.post("/jobs", json={"job_description": JD})

    assert response.status_code == 201


async def test_the_answer_loop_is_rate_limited_and_keyed_by_interview(app, client):
    """Keyed by interview, which is what a candidate's token is scoped to - so one candidate's
    pace never constrains another's.

    The budget is deliberately set above the length of any real interview, so it cannot be
    reached by answering: the interview finishes first. Exhausting the bucket directly is
    therefore the only way to observe the binding, and it proves precisely the two things that
    matter - which bucket the route charges, and which identity it charges it against.
    """
    _, interview_a, token_a = await _interview(client)
    _, interview_b, token_b = await _interview(client)

    # Spend interview A's budget without touching interview B's.
    limiter = app.state.rate_limiter
    for _ in range(LIMITS["answer_interview"][0].count):
        limiter.check(("answer_interview", interview_a))

    answer = {"answer": "I designed a PostgreSQL schema and served it through FastAPI."}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as candidate:
        refused = await candidate.post(
            f"/interviews/{interview_a}/answers",
            json=await answer_payload(
                candidate,
                f"/interviews/{interview_a}/answers",
                answer,
                {"Authorization": f"Bearer {token_a}"},
            ),
            headers={"Authorization": f"Bearer {token_a}"},
        )
        unaffected = await candidate.post(
            f"/interviews/{interview_b}/answers",
            json=await answer_payload(
                candidate,
                f"/interviews/{interview_b}/answers",
                answer,
                {"Authorization": f"Bearer {token_b}"},
            ),
            headers={"Authorization": f"Bearer {token_b}"},
        )

    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) > 0
    assert unaffected.status_code == 200


async def test_the_answer_budget_is_not_reached_by_a_real_interview(app, client):
    """The other half of the previous test: a budget that a genuine candidate could trip would
    be a correctness bug, not a security control. Answering this interview to completion must
    never produce a 429."""
    _, interview_id, token = await _interview(client)

    statuses = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as candidate:
        headers = {"Authorization": f"Bearer {token}"}
        for _ in range(LIMITS["answer_interview"][0].count):
            response = await candidate.post(
                f"/interviews/{interview_id}/answers",
                json=await answer_payload(
                    candidate,
                    f"/interviews/{interview_id}/answers",
                    {"answer": "I used PostgreSQL and Python to build and ship a service."},
                    headers,
                ),
                headers=headers,
            )
            statuses.append(response.status_code)
            if response.status_code == 409:  # the interview finished, as it should
                break

    assert 429 not in statuses
    assert statuses[-1] == 409, "expected the interview to complete before the budget ran out"


async def test_an_unauthorized_caller_cannot_spend_a_real_candidates_budget(app, client):
    """Authorization runs before the budget. If it did not, anyone knowing an interview id
    could exhaust that interview's allowance and lock out the actual candidate."""
    _, interview_id, token = await _interview(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as attacker:
        for _ in range(LIMITS["answer_interview"][0].count + 5):
            response = await attacker.post(
                f"/interviews/{interview_id}/answers",
                json=await answer_payload(
                    attacker,
                    f"/interviews/{interview_id}/answers",
                    {"answer": "spam"},
                    {"Authorization": "Bearer not-the-right-token"},
                ),
                headers={"Authorization": "Bearer not-the-right-token"},
            )
            assert response.status_code == 401

    # The real candidate is unaffected.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as candidate:
        response = await candidate.post(
            f"/interviews/{interview_id}/answers",
            json=await answer_payload(
                candidate,
                f"/interviews/{interview_id}/answers",
                {"answer": "I built a FastAPI service backed by PostgreSQL."},
                {"Authorization": f"Bearer {token}"},
            ),
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200


async def test_report_generation_is_budgeted_on_the_candidate_listing_too(app, client):
    """``GET /jobs/{id}/interviews`` also generates reports on its cache-miss path, so it spends
    the same LLM work as the report endpoint and is charged the same allowance.

    An exhausted budget must degrade the row rather than fail the request: the recruiter still
    sees who was invited, and the score arrives on a later load. A 429 for the whole listing
    would let one job with several freshly completed interviews take down the candidate table.
    """
    job_id, interview_id, token = await _interview(client)

    # Finish the interview so the listing has something to generate a report for.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as candidate:
        headers = {"Authorization": f"Bearer {token}"}
        for _ in range(LIMITS["answer_interview"][0].count):
            response = await candidate.post(
                f"/interviews/{interview_id}/answers",
                json=await answer_payload(
                    candidate,
                    f"/interviews/{interview_id}/answers",
                    {"answer": "I used PostgreSQL and Python to build and ship a service."},
                    headers,
                ),
                headers=headers,
            )
            if response.status_code == 409:
                break
    assert response.status_code == 409, "expected the interview to complete"

    # Spend the whole report allowance before the listing runs.
    limiter = app.state.rate_limiter
    recruiter_id = next(iter(app.state.recruiter_session_store._sessions.values())).recruiter_id
    for _ in range(LIMITS["report_recruiter"][0].count):
        limiter.check(("report_recruiter", recruiter_id))

    listing = await client.get(f"/jobs/{job_id}/interviews")

    assert listing.status_code == 200, "an exhausted budget must not fail the whole listing"
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["interview_id"] == interview_id
    assert rows[0]["overall_score"] is None, "no report should have been generated"


async def test_a_429_carries_no_detail_about_which_budget_was_hit(app, anonymous):
    _spend(app, "signup_global", 3600, _window("signup_global", 3600).count)

    refused = await anonymous.post(
        "/auth/recruiter/signup", json=recruiter_credentials("extra@intermind.test")
    )

    assert refused.status_code == 429
    assert refused.json() == {"detail": "Too many requests. Please try again later."}
    for revealing in ("signup_global", "bucket", "limit", "quota"):
        assert revealing not in refused.text


# =================================================================================================
# 3. Input size limits, enforced before the expensive work
# =================================================================================================


async def test_an_oversized_job_description_is_rejected(client):
    response = await client.post(
        "/jobs", json={"job_description": "x" * (MAX_JOB_DESCRIPTION_CHARS + 1)}
    )

    assert response.status_code == 422


async def test_a_job_description_at_the_limit_is_still_accepted(client):
    """The bound is resource protection, not product policy - a long real JD must still work."""
    response = await client.post(
        "/jobs", json={"job_description": "Backend Engineer. Python. " + "detail " * 100}
    )

    assert response.status_code == 201


async def test_an_oversized_job_description_never_reaches_the_llm(app, client):
    """The point of enforcing size during request validation: the handler never runs, so the
    analysis call it would have made is never paid for."""
    from app.api.deps import get_llm_client

    calls = []

    class RecordingLLM:
        async def structured(self, *args, **kwargs):  # pragma: no cover - must never run
            calls.append(1)
            raise AssertionError("the LLM was called for an oversized job description")

    app.dependency_overrides[get_llm_client] = lambda: RecordingLLM()

    response = await client.post(
        "/jobs", json={"job_description": "x" * (MAX_JOB_DESCRIPTION_CHARS + 1)}
    )

    assert response.status_code == 422
    assert not calls


async def test_an_oversized_answer_is_rejected(app, client):
    _, interview_id, token = await _interview(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as candidate:
        response = await candidate.post(
            f"/interviews/{interview_id}/answers",
            json=await answer_payload(
                candidate,
                f"/interviews/{interview_id}/answers",
                {"answer": "y" * (MAX_ANSWER_CHARS + 1)},
                {"Authorization": f"Bearer {token}"},
            ),
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 422


async def test_a_normal_length_answer_is_still_accepted(app, client):
    _, interview_id, token = await _interview(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as candidate:
        response = await candidate.post(
            f"/interviews/{interview_id}/answers",
            json=await answer_payload(
                candidate,
                f"/interviews/{interview_id}/answers",
                {"answer": "I designed a PostgreSQL schema and served it through FastAPI. " * 20},
                {"Authorization": f"Bearer {token}"},
            ),
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200


async def test_oversized_candidate_identity_fields_are_rejected(client):
    job_id = await _job(client)
    await client.post(f"/jobs/{job_id}/interview-plan")

    response = await client.post(
        "/interviews", json={"job_id": job_id, "candidate_name": "n" * 1_000}
    )

    assert response.status_code == 422


# =================================================================================================
# 4. Azure Speech credential issuance
# =================================================================================================


async def test_a_completed_interview_is_refused_speech_credentials(app, client, monkeypatch):
    """A finished interview accepts no further answers, so it has no use for a microphone -
    and issuing Azure credentials for one spends a real resource on a dead session."""
    from app.core.config import Settings, get_settings
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, speech_provider="azure", azure_speech_key=None,
        azure_speech_resource_id=None,
    )
    from app.api.routes import speech as speech_route
    from app.domain.interview import InterviewStatus

    _, interview_id, token = await _interview(client)

    class CompletedState:
        status = InterviewStatus.COMPLETED

    async def completed(_sessions, _interview_id):
        return CompletedState()

    monkeypatch.setattr(
        speech_route.InterviewSessionService, "get_state", completed, raising=True
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as candidate:
        response = await candidate.get(
            f"/interviews/{interview_id}/speech-token",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 409


async def test_a_token_for_one_interview_does_not_mint_credentials_for_another(app, client):
    """Interview A's candidate token must not reach interview B's Speech endpoint."""
    _, interview_a, token_a = await _interview(client)
    _, interview_b, _ = await _interview(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as candidate:
        response = await candidate.get(
            f"/interviews/{interview_b}/speech-token",
            headers={"Authorization": f"Bearer {token_a}"},
        )

    assert response.status_code == 401
    assert interview_a != interview_b


async def test_an_invalid_token_is_refused_speech_credentials(app, client):
    _, interview_id, _ = await _interview(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as candidate:
        response = await candidate.get(
            f"/interviews/{interview_id}/speech-token",
            headers={"Authorization": "Bearer definitely-not-a-real-token"},
        )

    assert response.status_code == 401


async def test_no_credential_at_all_is_refused_speech_credentials(app, client):
    _, interview_id, _ = await _interview(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        response = await anon.get(f"/interviews/{interview_id}/speech-token")

    assert response.status_code == 401


# =================================================================================================
# 5. A rejected password is never reflected
# =================================================================================================


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"email": EMAIL, "password": PASSWORD_CANARY * 60}, id="too-long"),
        pytest.param({"email": EMAIL, "password": {"n": PASSWORD_CANARY}}, id="wrong-type"),
        pytest.param({"email": EMAIL, "password": [PASSWORD_CANARY]}, id="array"),
    ],
)
async def test_signup_never_echoes_the_submitted_password(anonymous, payload):
    """The finding: FastAPI's default validation handler returns pydantic's ``input`` key, which
    is the rejected value itself - so a password that failed validation came straight back in
    the 422 body, and from there into devtools, proxy logs and error trackers.

    Asserted against the entire response body, not a particular key, because the leak was never
    about one field's name."""
    response = await anonymous.post("/auth/recruiter/signup", json=payload)

    assert response.status_code == 422
    assert PASSWORD_CANARY not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"email": EMAIL, "password": PASSWORD_CANARY * 60}, id="too-long"),
        pytest.param({"email": EMAIL, "password": {"n": PASSWORD_CANARY}}, id="wrong-type"),
    ],
)
async def test_login_never_echoes_the_submitted_password(anonymous, payload):
    response = await anonymous.post("/auth/recruiter/login", json=payload)

    assert response.status_code == 422
    assert PASSWORD_CANARY not in response.text


async def test_validation_errors_still_say_which_field_is_wrong(anonymous):
    """The fix must not reduce a 422 to an opaque failure: the field and the reason are what
    make it actionable, and the frontend renders ``msg`` (see frontend/src/api/client.ts)."""
    response = await anonymous.post(
        "/auth/recruiter/signup",
        json={"email": EMAIL, "password": PASSWORD_CANARY * 60},
    )

    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "password"]
    assert error["msg"]
    assert error["type"] == "string_too_long"
    assert "input" not in error
    assert "ctx" not in error


async def test_the_password_is_not_reflected_by_the_policy_rejection_either(anonymous):
    """The other way a password is refused: too short, which is a domain error rather than a
    pydantic one and so takes an entirely different response path."""
    response = await anonymous.post(
        "/auth/recruiter/signup", json={"email": EMAIL, "password": "short"}
    )

    assert response.status_code == 422
    assert "short" not in response.json()["detail"] or "at least" in response.json()["detail"]
    assert response.json()["detail"] == "Password must be at least 12 characters."


async def test_an_oversized_answer_is_not_echoed_back_either(app, client):
    """The same root cause applied to every field, so the fix is verified on a second one - a
    candidate's answer is the recruiter's data and must not be reflected either."""
    _, interview_id, token = await _interview(client)
    marker = "ANSWER-CANARY-7b2d"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as candidate:
        response = await candidate.post(
            f"/interviews/{interview_id}/answers",
            json=await answer_payload(
                candidate,
                f"/interviews/{interview_id}/answers",
                {"answer": marker + "z" * MAX_ANSWER_CHARS},
                {"Authorization": f"Bearer {token}"},
            ),
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 422
    assert marker not in response.text
