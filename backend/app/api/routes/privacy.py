"""Authenticated erasure and opt-in scheduled retention."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.auth import current_recruiter_id
from app.core.config import Settings, get_settings
from app.privacy.retention import (
    delete_interview_for_recruiter,
    purge_expired_interviews,
    purge_orphan_data,
)

router = APIRouter(tags=["privacy"])


@router.delete("/interviews/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_owned_interview(
    interview_id: str,
    request: Request,
    recruiter_id: str = Depends(current_recruiter_id),
) -> None:
    """Erase one owned interview, its report, activity and unshared candidate row."""
    sessions = getattr(request.app.state, "db_session_factory", None)
    if sessions is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Persistent storage required")
    await delete_interview_for_recruiter(
        sessions, interview_id=interview_id, recruiter_id=recruiter_id
    )


@router.get("/internal/retention/purge", include_in_schema=False)
async def scheduled_retention(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, int]:
    """Daily Vercel Cron; disabled by default and unusable without a configured secret."""
    if not settings.retention_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    supplied = request.headers.get("authorization", "")
    expected = f"Bearer {settings.cron_secret}" if settings.cron_secret else ""
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    sessions = getattr(request.app.state, "db_session_factory", None)
    if sessions is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Persistent storage required")
    deleted = await purge_expired_interviews(
        sessions, retention_days=settings.interview_retention_days
    )
    candidates, activity = await purge_orphan_data(
        sessions, retention_days=settings.interview_retention_days
    )
    return {
        "deleted_interviews": deleted,
        "deleted_orphan_candidates": candidates,
        "deleted_orphan_activity": activity,
    }
