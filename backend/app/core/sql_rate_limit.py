"""PostgreSQL-backed exact rolling windows for independently scaled API instances."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from math import ceil

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.limits import LIMITS
from app.core.rate_limit import RateLimiter, RateLimitExceeded
from app.db.models import RateLimitEventRow

# Transaction-scoped advisory lock, deliberately one key for every admission. Low-traffic
# portfolio requests serialize briefly; all named budgets either commit together or not at all.
# Unlike a process mutex, this also works across Vercel instances and Neon transaction pooling.
_ADMISSION_LOCK = 0x494E5445524D494E
_MAX_EVENTS = 200_000
_LONGEST_WINDOW = max(limit.seconds for limits in LIMITS.values() for limit in limits)


class SqlRateLimiter:
    def __init__(
        self,
        sessions: async_sessionmaker,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sessions = sessions
        self._clock = clock

    async def check(self, *buckets: tuple[str, str]) -> None:
        keys = RateLimiter._keys(buckets)
        if not keys:
            return
        now = self._clock()
        refusal: int | None = None
        async with self._sessions.begin() as db:
            # Held until commit or rollback. A failed DB call never admits a request.
            await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADMISSION_LOCK})
            await db.execute(
                delete(RateLimitEventRow).where(
                    RateLimitEventRow.admitted_at <= now - timedelta(seconds=_LONGEST_WINDOW)
                )
            )
            retry_after = 0
            for bucket, identity, window in keys:
                count, oldest = (await db.execute(
                    select(func.count(), func.min(RateLimitEventRow.admitted_at)).where(
                        RateLimitEventRow.bucket == bucket,
                        RateLimitEventRow.identity == identity,
                        RateLimitEventRow.window_seconds == window,
                        RateLimitEventRow.admitted_at > now - timedelta(seconds=window),
                    )
                )).one()
                ceiling = next(limit.count for limit in LIMITS[bucket] if limit.seconds == window)
                if count >= ceiling:
                    wait = (oldest + timedelta(seconds=window) - now).total_seconds()
                    retry_after = max(retry_after, ceil(wait))
            if retry_after:
                refusal = max(1, retry_after)
            else:
                total = (
                    await db.execute(select(func.count()).select_from(RateLimitEventRow))
                ).scalar_one()
                if total + len(keys) > _MAX_EVENTS:
                    refusal = 60
                else:
                    db.add_all(
                        RateLimitEventRow(
                            bucket=bucket, identity=identity,
                            window_seconds=window, admitted_at=now,
                        )
                        for bucket, identity, window in keys
                    )
        # Commit stale-event pruning even after refusing admission. Otherwise a full table
        # would roll the cleanup back on every denied request and could stay locked out.
        if refusal is not None:
            raise RateLimitExceeded(refusal)
