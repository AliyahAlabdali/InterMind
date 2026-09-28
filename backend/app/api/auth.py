"""The recruiter/candidate access boundary.

Makes the information split that already runs through this codebase (``InterviewResponse`` vs.
``InterviewReport``/``CandidateSessionSummary`` - see ``app.api.schemas``) an enforced one,
rather than relying on "the frontend simply never calls that endpoint", which anyone with an
interview id and an HTTP client can bypass.

Two checks, over two separate credential types that never mix:

- :func:`require_recruiter_access` - satisfied **only** by a live recruiter session cookie. The
  recruiter signs in with their own registered account's email and password
  (``app.api.routes.auth``), and the browser holds nothing but an opaque, expiring, revocable
  session identifier. Guards the endpoints that expose evaluation internals
  (scores/evidence/weaknesses/strengths), list other candidates' sessions, or write job data.

- :func:`require_candidate_access` - scoped to exactly one interview id, via the random,
  unguessable ``InterviewSession.access_token`` minted when that interview starts. A recruiter
  session also satisfies this: a recruiter can always see what a candidate can see. That
  override is one-directional and deliberate. The reverse never holds - a candidate token is
  checked only against its own interview's record, and is never consulted by
  ``require_recruiter_access``.

- :func:`require_interview_plan_access` - the same two credentials against a *job's* plan, and
  the one place the answer is not simply yes or no: the job's owner gets the whole plan, a
  candidate interviewing for that job gets only the part their own screen needs. See that
  function and ``app.api.routes.interview_plans``.

Recruiter identity comes from a self-registered account (``app.api.routes.auth``), and every
recruiter-scoped query resolves its owner through :func:`current_recruiter_id`. See
``docs/recruiter-auth.md`` for the full shape of that and what production would still need.

**What this boundary does NOT cover:** ``GET /jobs/{job_id}`` is deliberately public, returning
the reduced ``PublicJobResponse`` (no ``job_description``) so a candidate's interview screen can
name the role it is interviewing for. ``POST /jobs`` and ``GET /jobs`` are recruiter-only and
owner-scoped. See ``app.api.routes.jobs`` for that split.
"""

from __future__ import annotations

import hmac
from enum import StrEnum

from fastapi import Cookie, Depends, Header

from app.api.deps import (
    get_interview_session_repository,
    get_job_repository,
    get_recruiter_session_store,
)
from app.api.recruiter_session import RecruiterSessionStore
from app.api.routes.auth import RECRUITER_SESSION_COOKIE
from app.core.exceptions import AccessDenied
from app.repositories.ports import InterviewSessionRepository, JobRepository


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _tokens_match(candidate: str, expected: str) -> bool:
    """Constant-time comparison - a token check is exactly the kind of comparison where a
    naive ``==`` can leak timing information about how much of the token was guessed correctly.
    Cheap to get right even at this milestone's scope."""
    return hmac.compare_digest(candidate, expected)


def _has_recruiter_session(store: RecruiterSessionStore, session_cookie: str | None) -> bool:
    return store.is_valid(session_cookie)


async def current_recruiter_id(
    session_cookie: str | None = Cookie(default=None, alias=RECRUITER_SESSION_COOKIE),
    store: RecruiterSessionStore = Depends(get_recruiter_session_store),
) -> str:
    """The authenticated recruiter's id, resolved from the session cookie.

    **The single source of truth for ownership.** Every recruiter-scoped query takes its
    ``recruiter_id`` from here. A request body can say whatever it likes about who owns a
    resource; nothing reads it.

    Raises:
        AccessDenied: no live session.
    """
    session = store.resolve(session_cookie)
    if session is None:
        raise AccessDenied("Recruiter sign-in required.")
    return session.recruiter_id


async def require_recruiter_access(
    session_cookie: str | None = Cookie(default=None, alias=RECRUITER_SESSION_COOKIE),
    store: RecruiterSessionStore = Depends(get_recruiter_session_store),
) -> None:
    """FastAPI dependency: raise :class:`AccessDenied` unless the caller holds a live recruiter
    session.

    **One mechanism, deliberately.** This used to also accept the shared recruiter credential as
    a bearer token, which was a second way in that existed only because the browser once needed
    it. The browser now signs in with an email and password (``app.api.routes.auth``) and holds
    an opaque session; leaving a long-lived shared bearer credential accepted alongside that
    would have meant the production boundary had two doors, one of which never expires and
    cannot be revoked.
    """
    if not store.is_valid(session_cookie):
        raise AccessDenied("Recruiter sign-in required.")


async def require_candidate_access(
    interview_id: str,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=RECRUITER_SESSION_COOKIE),
    store: RecruiterSessionStore = Depends(get_recruiter_session_store),
    session_repo: InterviewSessionRepository = Depends(get_interview_session_repository),
) -> None:
    """FastAPI dependency: raise :class:`AccessDenied` unless the caller presents either the
    recruiter token or this specific interview's own ``access_token``.

    ``interview_id`` is taken directly from the route's own path parameter (FastAPI wires
    dependency parameters to path parameters of the same name automatically) - this is what
    makes the check "scoped to the specific interview it was issued for" rather than a bare
    "is this *a* valid candidate token" check: interview A's token never satisfies a request
    for interview B, because the comparison is always against *this* interview_id's own
    session record.

    Propagates ``InterviewNotFound`` (via ``session_repo.get``) unchanged for an unknown
    interview id - the same 404 the route itself would eventually raise, not a new error shape.

    A recruiter *session* satisfies this the same way the recruiter bearer token always has -
    the boundary is one-directional by design and that is unchanged. The reverse is not true and
    must never become true: a candidate's interview token is checked only against that one
    interview's own record, and is never consulted by ``require_recruiter_access``. The two
    credentials are separate types, checked by separate code paths, against separate stores.
    """
    # A recruiter may reach a candidate's interview - but only one of *their own* candidates.
    #
    # This override used to accept any recruiter, which was correct when there was exactly one.
    # With multiple recruiters it meant Recruiter B could read Recruiter A's interview: the
    # candidate's name, email, every question and every answer. Scoping it through the owning
    # job keeps the intended behaviour (a recruiter can see what their candidate sees) and
    # removes the cross-tenant hole. Candidate tokens are unaffected and are still checked
    # exactly as before, below.
    recruiter_session = store.resolve(session_cookie)
    if recruiter_session is not None:
        await session_repo.get_for_recruiter(interview_id, recruiter_session.recruiter_id)
        return
    token = _extract_bearer_token(authorization)
    if not token:
        raise AccessDenied("Access token missing.")
    session = await session_repo.get(interview_id)
    if not _tokens_match(token, session.access_token):
        raise AccessDenied("Access token is not valid for this interview.")


class PlanAudience(StrEnum):
    """Who is asking for a job's interview plan, and therefore how much of it they may see."""

    RECRUITER = "recruiter"
    CANDIDATE = "candidate"


async def require_interview_plan_access(
    job_id: str,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=RECRUITER_SESSION_COOKIE),
    store: RecruiterSessionStore = Depends(get_recruiter_session_store),
    job_repo: JobRepository = Depends(get_job_repository),
    session_repo: InterviewSessionRepository = Depends(get_interview_session_repository),
) -> PlanAudience:
    """FastAPI dependency: who may read ``job_id``'s interview plan, and in what shape.

    The plan is the recruiter's assessment strategy for a role - every competency, technology
    and task the interview may probe, with its requirement level and O*NET grounding. It used
    to be readable by anyone who knew a job id, which predates multiple recruiters: with one
    account there was no other tenant to leak to. With many, a job id was enough to read a
    competitor's hiring criteria, and ``POST`` was enough to generate a plan on their job.

    Two credentials, resolved in the same order and with the same primitives as
    :func:`require_candidate_access`:

    * **The owning recruiter.** Scoped through ``get_for_recruiter``, so another recruiter's job
      raises ``JobNotFound`` (404) rather than 403 - consistent with every other recruiter route
      here, and it does not confirm that the job exists.
    * **A candidate interviewing for this job**, holding that interview's own access token. The
      token is matched against the sessions belonging to *this* job, so a token for a different
      job never satisfies the check. They receive the reduced candidate shape, never the plan
      itself - see ``app.api.routes.interview_plans``.

    Anything else is 401, with the same message whether or not the job exists.

    Raises:
        app.core.exceptions.JobNotFound: a signed-in recruiter asked for a job they do not own.
        app.core.exceptions.AccessDenied: no usable credential was presented.
    """
    recruiter_session = store.resolve(session_cookie)
    if recruiter_session is not None:
        await job_repo.get_for_recruiter(job_id, recruiter_session.recruiter_id)
        return PlanAudience.RECRUITER

    token = _extract_bearer_token(authorization)
    if token:
        # Compared against this job's own interviews only. `list_by_job` on an unknown job is an
        # empty list, so an invalid token and a non-existent job are indistinguishable from the
        # outside, which is the same property the 404-not-403 convention buys elsewhere.
        for session in await session_repo.list_by_job(job_id):
            if _tokens_match(token, session.access_token):
                return PlanAudience.CANDIDATE

    raise AccessDenied("Recruiter sign-in or this interview's access token is required.")
