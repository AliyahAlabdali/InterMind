"""Milestone 4 recruiter/candidate access boundary.

This is a deliberately small, milestone-scoped authorization mechanism - NOT production
authentication. It exists to make the candidate/recruiter information boundary that already
runs through this codebase (``InterviewResponse`` vs. ``InterviewReport``/
``CandidateSessionSummary`` - see ``app.api.schemas``) actually enforceable, instead of relying
on "the frontend simply never calls that endpoint" (which anyone with the interview id and an
HTTP client can bypass).

Two bearer-token checks, both opaque strings compared with :func:`hmac.compare_digest`:

- :func:`require_recruiter_access` - a single shared secret (``Settings.
  recruiter_access_token``), standing in for "is a recruiter" for the whole app. There are no
  recruiter accounts, roles, or sessions at this milestone - every recruiter uses the same
  token, configured once per deployment via the ``RECRUITER_ACCESS_TOKEN`` env var. Guards the
  endpoints that expose evaluation internals (scores/evidence/weaknesses/strengths) or list
  other candidates' sessions.
- :func:`require_candidate_access` - scoped to exactly one interview id, via the random,
  unguessable ``InterviewSession.access_token`` minted when that interview starts (itself only
  reachable with a valid recruiter token - see ``POST /interviews``). A valid recruiter token
  also satisfies this check (a recruiter can always see what a candidate can see; the boundary
  is one-directional - see the module docstring above), but a candidate token for interview A
  never satisfies a request for interview B.

Explicitly out of scope here, and left for Milestone 6-B productionization: real recruiter
accounts/identity, password or OAuth login, token expiry/rotation/revocation, per-recruiter
audit trails, and any persistent (non-in-memory) credential store. Nothing below should be
mistaken for that; it exists only to make "recruiter-only" and "this candidate's own interview"
real, enforced boundaries instead of documentation comments.

**What this boundary does NOT cover yet:** ``app.api.routes.jobs`` (job creation/lookup/
listing) and ``app.api.routes.interview_plans`` (interview-plan creation/lookup) call neither
dependency below and remain fully public - anyone who can reach the API can create a job,
read/list any job, or create/read an interview plan. That is a real gap, not an oversight: M4's
guarantee is specifically the interview-level candidate/recruiter boundary (own interview vs.
recruiter-only report/candidate-listing/start), not resource-level authorization for every
recruiter-owned resource. Locking down jobs/job-analysis/interview-plans is Milestone 6-B
productionization work, tracked there - do not treat those endpoints as protected until then.
"""

from __future__ import annotations

import hmac

from fastapi import Depends, Header

from app.api.deps import get_interview_session_repository
from app.core.config import Settings, get_settings
from app.core.exceptions import AccessDenied
from app.repositories.ports import InterviewSessionRepository


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


async def require_recruiter_access(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """FastAPI dependency: raise :class:`AccessDenied` unless ``Authorization: Bearer <token>``
    carries the shared recruiter token. Use on every recruiter-only endpoint (evaluation
    scores/evidence/weaknesses, candidate listings, starting a new interview session)."""
    token = _extract_bearer_token(authorization)
    if not token or not _tokens_match(token, settings.recruiter_access_token):
        raise AccessDenied("Recruiter access token missing or invalid.")


async def require_candidate_access(
    interview_id: str,
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
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
    """
    token = _extract_bearer_token(authorization)
    if not token:
        raise AccessDenied("Access token missing.")
    if _tokens_match(token, settings.recruiter_access_token):
        return  # a recruiter may always reach a candidate's own interview endpoints
    session = await session_repo.get(interview_id)
    if not _tokens_match(token, session.access_token):
        raise AccessDenied("Access token is not valid for this interview.")
