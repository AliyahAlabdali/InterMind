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
# Sign-up and sign-in are budgeted **deployment-wide**, not per caller. They have no
# authenticated identity to key on, and this deployment has no trustworthy per-visitor identity
# either: browser traffic reaches the API through a proxy, so every request arrives at the
# application carrying the same link-local proxy address. A per-address bucket would have
# throttled every visitor as one while describing itself as per-visitor protection, so it is
# not offered. See docs/public-launch-security.md.
#
# Every other bucket is keyed by an identity the request actually proves - the signed-in
# recruiter's account, or the interview a candidate's token is scoped to - and each carries a
# deployment-wide companion. Those identities cannot be minted freely: accounts are bounded by
# the sign-up ceiling and interviews by the invite ceiling, which is what keeps the limiter's
# key space bounded (see app.core.rate_limit.RateLimiter.check).
LIMITS: dict[str, tuple[Limit, ...]] = {
    # Account creation. Costs a scrypt hash and creates durable state.
    "signup_global": (Limit(50, 3600), Limit(100, 86400)),
    # Sign-in. Never keyed by the submitted email: a budget that trips only for addresses that
    # exist would be exactly the account-existence oracle the uniform login response in
    # app.api.routes.auth exists to prevent.
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
