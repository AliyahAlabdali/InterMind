"""Server-side recruiter sessions.

Why this exists
---------------
The recruiter credential used to reach the browser: ``VITE_RECRUITER_ACCESS_TOKEN`` was inlined
into the production JavaScript bundle by Vite, so anyone who loaded the site could read the
shared recruiter secret out of ``dist/assets/*.js`` and call every recruiter-only endpoint. The
server-side boundary in ``app.api.auth`` was correctly enforced; the problem was that the key to
it was published.

The fix is this indirection. The browser posts the credential once to a login endpoint, the
server checks it and hands back an opaque session identifier in an ``HttpOnly`` cookie, and the
underlying credential never leaves the server. A stolen session identifier is revocable and
expires; the credential behind it is not exposed at all.

What a session carries
----------------------
One recruiter's id. Accounts are real now: recruiters register themselves, their credential is a
``scrypt`` hash in the recruiter repository, and every session is minted for the account that
signed in (see ``app.api.routes.auth`` and ``docs/recruiter-auth.md``). ``session.recruiter_id``
is what :func:`app.api.auth.current_recruiter_id` resolves, and therefore what every
owner-scoped query is scoped by - so sessions are per-account, not interchangeable.

What this is not
----------------
Still not an identity platform: no roles, no teams, no password reset or email verification, and
no per-recruiter audit trail beyond the activity feed.

The default ``RecruiterSessionStore`` is in-memory and does not survive a restart.
``SqlRecruiterSessionStore`` is opt-in for deployments with multiple instances; it retains the
same cookie contract and stores only a SHA-256 digest of each high-entropy session token.
"""

from __future__ import annotations

import hashlib
import inspect
import secrets
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TypeVar

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.exceptions import RecruiterEmailTaken
from app.db.models import RecruiterRow, RecruiterSessionRow
from app.domain.recruiter import Recruiter, normalize_email

#: Length of the session identifier in bytes before base64url encoding. 32 bytes of
#: `secrets` entropy is far beyond guessable and matches the candidate access tokens.
_SESSION_BYTES = 32


@dataclass(frozen=True)
class RecruiterSession:
    """One signed-in recruiter browser, and which recruiter it is.

    ``recruiter_id`` is the authority for every ownership decision in the product. It is written
    here at sign-in from the verified account and is never influenced by anything the client
    sends - a request cannot name the recruiter it wants to be.
    """

    token: str
    recruiter_id: str
    expires_at: datetime

    def is_expired(self, now: datetime | None = None) -> bool:
        return (now or datetime.now(UTC)) >= self.expires_at


@dataclass
class RecruiterSessionStore:
    """In-memory store of live recruiter sessions, keyed by session token.

    Process-lifetime only, like every other repository at this milestone (see
    ``app.repositories.in_memory``). Held on ``app.state`` so it is one instance per application.
    """

    ttl_seconds: int
    _sessions: dict[str, RecruiterSession] = field(default_factory=dict)

    def create(self, recruiter_id: str) -> RecruiterSession:
        """Mint a session for ``recruiter_id``. The token is unpredictable and is the only thing
        the browser ever receives - never the credential it was exchanged for."""
        self._prune()
        session = RecruiterSession(
            token=secrets.token_urlsafe(_SESSION_BYTES),
            recruiter_id=recruiter_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.ttl_seconds),
        )
        self._sessions[session.token] = session
        return session

    def resolve(self, token: str | None) -> RecruiterSession | None:
        """Return the live session for ``token``, or ``None``.

        The single place a cookie becomes an identity. An expired session is dropped on the way
        past rather than left to accumulate, so an expired cookie behaves exactly like an
        unknown one.
        """
        if not token:
            return None
        session = self._sessions.get(token)
        if session is None:
            return None
        if session.is_expired():
            del self._sessions[token]
            return None
        return session

    def is_valid(self, token: str | None) -> bool:
        """Whether ``token`` names a live, unexpired session.

        An expired session is dropped on the way past rather than left to accumulate, so an
        expired cookie behaves exactly like an unknown one.
        """
        return self.resolve(token) is not None

    def revoke(self, token: str | None) -> None:
        """Log out. Idempotent: revoking an unknown or already-expired session is not an error,
        because the caller's intent - "this session must not work any more" - is satisfied."""
        if token:
            self._sessions.pop(token, None)

    def _prune(self) -> None:
        now = datetime.now(UTC)
        for token in [t for t, s in self._sessions.items() if s.is_expired(now)]:
            del self._sessions[token]

    @property
    def active_count(self) -> int:
        """Live sessions, for tests. Not exposed through the API."""
        self._prune()
        return len(self._sessions)


class SqlRecruiterSessionStore:
    """Shared session store. Only a SHA-256 digest of the random cookie reaches PostgreSQL."""

    def __init__(self, sessions: async_sessionmaker, *, ttl_seconds: int) -> None:
        self._sessions = sessions
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _mint(self, recruiter_id: str) -> RecruiterSession:
        return RecruiterSession(
            token=secrets.token_urlsafe(_SESSION_BYTES),
            recruiter_id=recruiter_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.ttl_seconds),
        )

    async def create_with_recruiter(self, recruiter: Recruiter) -> RecruiterSession:
        """Commit sign-up and its first browser session as one durable operation."""
        issued = self._mint(recruiter.id)
        try:
            async with self._sessions.begin() as db:
                await db.execute(
                    delete(RecruiterSessionRow).where(
                        RecruiterSessionRow.expires_at <= datetime.now(UTC)
                    )
                )
                db.add(RecruiterRow(
                    id=recruiter.id,
                    email=normalize_email(recruiter.email),
                    password_hash=recruiter.password_hash,
                    created_at=recruiter.created_at,
                ))
                db.add(RecruiterSessionRow(
                    token_hash=self._digest(issued.token),
                    recruiter_id=recruiter.id,
                    expires_at=issued.expires_at,
                ))
        except IntegrityError as exc:
            raise RecruiterEmailTaken("An account with that email already exists.") from exc
        return issued

    async def create(self, recruiter_id: str) -> RecruiterSession:
        session = self._mint(recruiter_id)
        async with self._sessions.begin() as db:
            await db.execute(
                delete(RecruiterSessionRow).where(
                    RecruiterSessionRow.expires_at <= datetime.now(UTC)
                )
            )
            db.add(RecruiterSessionRow(
                token_hash=self._digest(session.token),
                recruiter_id=recruiter_id,
                expires_at=session.expires_at,
            ))
        return session

    async def resolve(self, token: str | None) -> RecruiterSession | None:
        if not token:
            return None
        async with self._sessions() as db:
            row = await db.get(RecruiterSessionRow, self._digest(token))
        if row is None or row.expires_at <= datetime.now(UTC):
            return None
        return RecruiterSession(
            token=token, recruiter_id=row.recruiter_id, expires_at=row.expires_at
        )

    async def is_valid(self, token: str | None) -> bool:
        return await self.resolve(token) is not None

    async def revoke(self, token: str | None) -> None:
        if token:
            async with self._sessions.begin() as db:
                await db.execute(
                    delete(RecruiterSessionRow).where(
                        RecruiterSessionRow.token_hash == self._digest(token)
                    )
                )


SessionStore = RecruiterSessionStore | SqlRecruiterSessionStore
_T = TypeVar("_T")


async def await_store_result(result: _T | Awaitable[_T]) -> _T:
    """Keep the existing synchronous in-memory test/deployment path while SQL uses async IO."""
    if inspect.isawaitable(result):
        return await result
    return result
