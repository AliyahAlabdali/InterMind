"""Admission control at the API boundary: who may spend how much of this deployment.

Ordering rule
-------------
**Authorization first, budgets second.** Every helper here is applied after the route's own
access check, never before it. Two reasons: a budget keyed by recruiter or interview identity
needs that identity to have been established, and charging an unauthenticated caller's budget
before deciding whether they may act at all would let anyone exhaust a legitimate user's
allowance by guessing ids.

The one exception is sign-up and sign-in, which have no authenticated identity to key on by
definition; those are charged only against their deployment-wide ceiling (see
:func:`limit_signup` / :func:`limit_login`).

Identity selection
------------------
Each budget is counted against whoever actually causes the cost, so one caller's traffic never
constrains another's:

- recruiter-initiated LLM work (job analysis, planning, reports, invitations) - the signed-in
  recruiter's account id, taken from the session, never from the request body;
- the candidate loop (answers, Speech credentials) - the interview id, which is what a
  candidate's own access token is scoped to.

Sign-up and sign-in: deployment-wide, not per visitor
-----------------------------------------------------
These two have no authenticated identity to key on, and this deployment has no trustworthy
per-visitor identity to substitute. Browser traffic reaches the API through a proxy, so every
request arrives at the application carrying the same link-local proxy address in
``request.client.host``. Keying on it would have put every visitor in one bucket while
describing itself as per-visitor protection - throttling unrelated people against each other
and reporting a guarantee that did not exist.

So both are charged only against their deployment-wide ceiling. That is a real cost control and
an honest one; it is **not** per-client brute-force protection, and nothing here should be read
as providing it. See ``docs/public-launch-security.md`` for the runtime evidence and for what
per-visitor limiting would require.

No forwarding header is read
----------------------------
``X-Forwarded-For``, ``X-Real-IP`` and ``Forwarded`` are never consulted, here or anywhere else
in the application. They are caller-supplied, so trusting one would let an attacker choose its
own bucket on every request - both a bypass and an unbounded source of dictionary keys. Reading
them safely needs a verified trusted-proxy design, which is a deliberate non-goal of this pass.
"""

from __future__ import annotations

from fastapi import Request

from app.core.rate_limit import RateLimiter


def get_rate_limiter(request: Request) -> RateLimiter:
    """The application's single limiter instance (created in ``app.main.create_app``)."""
    return request.app.state.rate_limiter


# --- Unauthenticated -------------------------------------------------------------------------


def limit_signup(request: Request) -> None:
    """Budget account creation deployment-wide: a scrypt hash plus durable state, on an open
    endpoint. Not a per-visitor limit - see the module docstring."""
    get_rate_limiter(request).check(("signup_global", "all"))


def limit_login(request: Request) -> None:
    """Budget sign-in attempts deployment-wide.

    **Never keyed by the submitted email.** A budget that tripped only for registered addresses
    would reveal exactly what the uniform "Incorrect email or password" response in
    ``app.api.routes.auth`` exists to hide. Every attempt is counted whether it succeeds or
    fails, so what a caller observes never depends on whether the account exists.

    Not a per-visitor limit, and therefore not per-client brute-force protection - see the
    module docstring for why none is available in this topology.
    """
    get_rate_limiter(request).check(("login_global", "all"))


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
