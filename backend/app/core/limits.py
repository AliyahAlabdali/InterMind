"""Central budgets for untrusted or expensive work.

Two unrelated kinds of ceiling live here on purpose, because both answer the same question -
"how much may one caller make this deployment do?" - and both must be readable in one place
when tuning them:

- :data:`LIMITS`, request-rate budgets enforced by :mod:`app.core.rate_limit`.
- The ``MAX_*_CHARS`` bounds, size budgets enforced by pydantic at the API boundary
  (``app.api.schemas``, ``app.api.routes.auth``) so an oversized body is rejected during request
  validation - before any handler runs, and therefore before any LLM call is made or any
  password is hashed.

Deployment limitations of the rate budgets (counters are process-local and reset on restart)
are documented in ``docs/public-launch-security.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- Input size bounds --------------------------------------------------------------------
# Deliberately generous: these are resource protection, not product policy. Each is far above
# any real value and is enforced before the expensive work it protects.

#: A job description. Long JDs exist; a megabyte of text billed to an LLM call does not.
MAX_JOB_DESCRIPTION_CHARS = 16_000

#: One candidate answer. Roughly 15 minutes of dictation, and well past any typed answer.
MAX_ANSWER_CHARS = 6_000

#: Candidate name/email as set by the recruiter when inviting. RFC 5321's forward-path bound.
MAX_IDENTITY_CHARS = 320


@dataclass(frozen=True)
class Limit:
    """``count`` admissions per rolling window of ``seconds``."""

    count: int
    seconds: int


# --- Request-rate budgets -------------------------------------------------------------------
#
# Rolling windows, not wall-clock buckets: a fixed bucket lets a caller spend the whole budget
# at :59 and the whole next one at :01. Failed attempts consume their admission too, or a wrong
# password would be free to retry.
#
# Every bucket an unauthenticated caller can key (``*_ip``) has a ``*_global`` companion. That
# pairing is what bounds the limiter's memory: once a global ceiling is reached the request is
# refused *before* any new per-identity key is recorded, so distinct source addresses cannot
# keep creating keys (see app.core.rate_limit.RateLimiter.check).
LIMITS: dict[str, tuple[Limit, ...]] = {
    # Account creation. Costs a scrypt hash and creates durable state.
    "signup_ip": (Limit(5, 3600),),
    "signup_global": (Limit(50, 3600), Limit(100, 86400)),
    # Sign-in. Keyed by source address and never by email: keying on the submitted address
    # would make the limiter itself an account-existence oracle, which is exactly what the
    # uniform login response in app.api.routes.auth exists to prevent.
    "login_ip": (Limit(10, 600),),
    "login_global": (Limit(100, 600),),
    # LLM-backed job-description analysis, per signed-in recruiter.
    "job_recruiter": (Limit(10, 3600), Limit(30, 86400)),
    "job_global": (Limit(60, 3600),),
    # LLM-backed interview-plan generation, per signed-in recruiter.
    "plan_recruiter": (Limit(20, 3600),),
    "plan_global": (Limit(60, 3600),),
    # Creating an interview (mints a candidate access token), per signed-in recruiter.
    "invite_recruiter": (Limit(20, 3600), Limit(50, 86400)),
    # The candidate loop: each answer runs evaluation and question generation. Keyed by
    # interview, so one candidate's pace never constrains another's.
    "answer_interview": (Limit(60, 600), Limit(200, 86400)),
    "answer_global": (Limit(300, 3600),),
    # Report generation, per signed-in recruiter. Only the first request per interview is
    # expensive (reports are cached), but the budget covers the cache-miss path.
    "report_recruiter": (Limit(30, 3600),),
    # Azure Speech credential issuance, per interview. A token lasts ~9 minutes, so a genuine
    # candidate needs a handful per interview; the ceiling is for the abusive case.
    "speech_interview": (Limit(60, 600), Limit(200, 86400)),
    "speech_global": (Limit(300, 3600), Limit(600, 86400)),
}
