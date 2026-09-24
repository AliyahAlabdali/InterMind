"""Recruiter activity feed - what the adaptive interviews have actually been doing.

Read-only view over the append-only log described in :mod:`app.domain.activity`. Recruiter-only
for the same reason the candidate listing is (see ``app.api.auth``): it names candidates and the
targets their answers produced evidence for, which is recruiter-side information.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.auth import current_recruiter_id
from app.api.deps import get_activity_repository
from app.domain.activity import ActivityEvent
from app.repositories.ports import ActivityRepository

router = APIRouter(tags=["activity"])


@router.get(
    "/activity",
    response_model=list[ActivityEvent],
)
async def list_activity(
    limit: int = Query(default=20, ge=1, le=100),
    recruiter_id: str = Depends(current_recruiter_id),
    activity_repo: ActivityRepository = Depends(get_activity_repository),
) -> list[ActivityEvent]:
    """Return this recruiter's most recent interview events, newest first.

    Scoped through the event's job to its owner. The feed names candidates and the targets they
    were assessed on, so an unscoped version would give every recruiter a live view of everyone
    else's interviews.

    Returns an empty list (not a 404) when nothing has happened yet - a workspace with no
    activity is a normal state, not an error.
    """
    return await activity_repo.list_recent_for_recruiter(recruiter_id, limit)
