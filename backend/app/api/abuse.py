"""Admission control at the API boundary: who may spend how much of this deployment.

Ordering rule
-------------
**Authorization first, budgets second.** Every helper here is applied after the route's own
access check, never before it. Two reasons: a budget keyed by recruiter or interview identity
needs that identity to have been established, and charging an unauthenticated caller's budget
before deciding whether they may act at all would let anyone exhaust a legitimate user's
allowance by guessing ids.

The one exception is sign-up and sign-in, which have no authenticated identity to key on by
definition; those are keyed by source address with a global companion (see
:func:`limit_signup` / :func:`limit_login`).

Identity selection
------------------
Each budget is counted against whoever actually causes the cost, so one caller's traffic never
constrains another's:

- recruiter-initiated LLM work (job analysis, planning, reports, invitations) - the signed-in
  recruiter's account id, from the session, never from the request body;
- the candidate loop (answers, Speech credentials) - the interview id, which is what a
  candidate's own access token is scoped to;
- unauthenticated auth endpoints - the transport source address, plus a global ceiling.

What is deliberately *not* used as a key
----------------------------------------
``X-Forwarded-For`` and ``X-Real-IP`` are never read. They are caller-supplied headers, so
trusting them here would turn the per-address budget into a free-form key an attacker sets to a
new value on every request - both a bypass and an unbounded source of dictionary keys. Only the
ASGI transport's own peer address is used. Behind a proxy that collapses many clients onto one
address this shares a bucket, which is conservative rather than a bypass; the global ceilings
are what actually bound cost in that case. See ``docs/public-launch-security.md``.
"""

from __future__ import annotations

from fastapi import Request

from app.core.rate_limit import RateLimiter

#: Stand-in identity for a request with no transport peer address (ASGI allows ``client`` to be
#: absent). Shares one bucket, which is the conservative reading.
_UNKNOWN_CLIENT = "unknown"


def get_rate_limiter(request: Request) -> RateLimiter:
    """The application's single limiter instance (created in ``app.main.create_app``)."""
    return request.app.state.rate_limiter


def _client_identity(request: Request) -> str:
    """The transport peer address. Never a caller-supplied header - see the module docstring."""
    return request.client.host if request.client else _UNKNOWN_CLIENT


# --- Unauthenticated -------------------------------------------------------------------------


def limit_signup(request: Request) -> None:
    """Budget account creation: a scrypt hash plus durable state, on an open endpoint."""
    identity = _client_identity(request)
    get_rate_limiter(request).check(("signup_ip", identity), ("signup_global", "all"))


def limit_login(request: Request) -> None:
    """Budget sign-in attempts.

    Keyed by source address and **never by the submitted email**. Keying on the email would
    make the limiter an account-existence oracle - a rate limit that only trips for registered
    addresses reveals exactly what the uniform "Incorrect email or password" response in
    ``app.api.routes.auth`` exists to hide. Every attempt is counted whether it succeeds or
    fails, so the response a caller sees is unchanged by whether the account exists.
    """
    identity = _client_identity(request)
    get_rate_limiter(request).check(("login_ip", identity), ("login_global", "all"))


# --- Recruiter-authenticated ------------------------------------------------------------------


def limit_job_analysis(request: Request, recruiter_id: str) -> None:
    """Budget LLM-backed job-description analysis (``POST /jobs``)."""
    get_rate_limiter(request).check(("job_recruiter", recruiter_id), ("job_global", "all"))


def limit_plan_generation(request: Request, recruiter_id: str) -> None:
    """Budget LLM-backed interview-plan generation (``POST /jobs/{id}/interview-plan``)."""
    get_rate_limiter(request).check(("plan_recruiter", recruiter_id), ("plan_global", "all"))


def limit_invite(request: Request, recruiter_id: str) -> None:
    """Budget interview creation (``POST /interviews``), which mints a candidate token."""
    get_rate_limiter(request).check(("invite_recruiter", recruiter_id))


def limit_report(request: Request, recruiter_id: str) -> None:
    """Budget report generation. Cached after the first call, so this covers the miss path."""
    get_rate_limiter(request).check(("report_recruiter", recruiter_id))


# --- Candidate / interview-scoped --------------------------------------------------------------


def limit_answer(request: Request, interview_id: str) -> None:
    """Budget the adaptive loop (``POST /interviews/{id}/answers``): evaluation + generation."""
    get_rate_limiter(request).check(
        ("answer_interview", interview_id), ("answer_global", "all")
    )


def limit_speech_token(request: Request, interview_id: str) -> None:
    """Budget Azure Speech credential issuance, per interview."""
    get_rate_limiter(request).check(
        ("speech_interview", interview_id), ("speech_global", "all")
    )
