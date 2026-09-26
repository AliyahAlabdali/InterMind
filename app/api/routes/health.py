"""Liveness endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    """Liveness, plus which storage backend is actually live.

    ``storage`` exists because the in-memory fallback is otherwise invisible from outside: a
    deployment that lost its ``DATABASE_URL`` would answer ``{"status": "ok"}`` while quietly
    discarding every account and report on the next restart. Reporting the mode makes that
    checkable straight after a deploy, without log access.

    It is a mode name and nothing else - never the URL, the host, the credentials, or whether the
    database is currently reachable. Callers learn only what this process decided to use at
    startup, which tells an attacker nothing they could not infer by watching data disappear.
    """
    return {
        "status": "ok",
        "storage": getattr(request.app.state, "storage_backend", "unknown"),
    }
