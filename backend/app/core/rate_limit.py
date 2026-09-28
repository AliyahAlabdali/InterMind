"""Atomic, bounded, process-local rolling-window admission control.

**What this is not.** Not a distributed quota and not a billing cap. Counters live in this
process: a restart clears them, and a second instance would enforce its own separate budget, so
N instances admit N times the configured rate. That is acceptable here only because the rest of
this backend is already single-process by design - recruiter sessions
(``app.api.recruiter_session``), the LangGraph checkpointer (``app.api.deps.get_interview_graph``)
and the interview lock registry (``app.services.interview_session.InterviewLockRegistry``) are
all in-process state, so a second instance would break sign-in and interviews long before it
weakened a rate limit. The deployment pins ``--workers 1`` for that reason; see
``docs/deployment.md`` and ``docs/public-launch-security.md``.

Three properties this implementation is responsible for:

**Atomicity.** A call consumes every budget it names, or none of them. Checking one bucket,
admitting, then failing on the next would let a refused request still spend the first budget.

**Bounded memory.** Two mechanisms. Expired windows are swept on every call, so a key stops
existing once its events age out. And because admission is refused *before* anything is
recorded, a bucket whose global ceiling is already reached cannot have new per-identity keys
created under it - so a caller cycling identities cannot keep growing the dictionary.
:data:`MAX_TRACKED_KEYS` is a backstop under both, so the table is bounded even if a future
caller introduces a bucket with no global companion.

**Concurrency safety.** The lock is a plain ``threading.Lock``: every operation here is
synchronous and short, nothing is awaited while it is held, and the process genuinely has other
threads (``asyncio.to_thread`` in ``app.services.speech_token``). Read-modify-write on the
counters is therefore indivisible with respect to both the event loop and those threads.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from math import ceil
from threading import Lock
from time import monotonic

from app.core.limits import LIMITS

#: Hard ceiling on distinct tracked (bucket, identity, window) keys. Sized far above what the
#: configured global budgets can produce, so reaching it means a bucket was added without a
#: global companion rather than that normal traffic arrived. At the ceiling new identities are
#: refused while identities already being tracked keep working, which fails closed for the
#: novel caller without locking out the legitimate one.
MAX_TRACKED_KEYS = 20_000


class RateLimitExceeded(Exception):
    """Raised when a budget is exhausted. Mapped to HTTP 429 in ``app.api.errors``."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__("Too many requests. Please try again later.")


class RateLimiter:
    """Rolling-window admission control over named budgets from :data:`app.core.limits.LIMITS`.

    One instance per application, held on ``app.state.rate_limiter`` (see ``app.main``).
    ``clock`` is injectable so tests can advance time without sleeping.
    """

    def __init__(self, *, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._lock = Lock()
        self._events: dict[tuple[str, str, int], deque[float]] = {}

    def check(self, *buckets: tuple[str, str]) -> None:
        """Consume every named budget together, or none of them.

        Each bucket is ``(name, identity)`` where ``name`` indexes :data:`LIMITS` and
        ``identity`` is the caller this budget is counted against.

        Neither the identity nor any submitted value is logged or included in the exception -
        the identity can be an account id or an interview id, and this type is raised on a
        path that ends in a response body.

        Raises:
            KeyError: ``name`` is not a configured bucket. A programming error, deliberately
                loud rather than silently unlimited.
            RateLimitExceeded: at least one budget is exhausted; nothing was consumed.
        """
        keys = self._keys(buckets)
        with self._lock:
            now = self._clock()
            self._sweep(now)
            retry_after = self._retry_after(keys, now)
            if retry_after:
                raise RateLimitExceeded(max(1, retry_after))
            # Refuse an unknown identity rather than grow past the backstop. Checked after the
            # budgets so a caller already being tracked is unaffected by table pressure.
            if len(self._events) >= MAX_TRACKED_KEYS and any(k not in self._events for k in keys):
                raise RateLimitExceeded(60)
            for key in keys:
                self._events.setdefault(key, deque()).append(now)

    @staticmethod
    def _keys(buckets: Iterable[tuple[str, str]]) -> list[tuple[str, str, int]]:
        """Expand ``(name, identity)`` pairs into one key per configured window.

        De-duplicated: a caller naming the same bucket twice must spend that budget once, not
        twice. ``LIMITS[name]`` raises ``KeyError`` on an unknown bucket - see :meth:`check`.
        """
        keys: list[tuple[str, str, int]] = []
        seen: set[tuple[str, str, int]] = set()
        for name, identity in buckets:
            for limit in LIMITS[name]:
                key = (name, identity, limit.seconds)
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
        return keys

    def _sweep(self, now: float) -> None:
        """Drop events that have aged out, and keys left empty by doing so."""
        for key in list(self._events):
            events = self._events[key]
            window = key[2]
            while events and events[0] <= now - window:
                events.popleft()
            if not events:
                del self._events[key]

    def _retry_after(self, keys: list[tuple[str, str, int]], now: float) -> int:
        """Seconds until the most constrained exhausted budget admits again; 0 if none is.

        The wait is until the *oldest* event in that window ages out, which is when the count
        next drops below the ceiling.
        """
        retry_after = 0
        for key in keys:
            name, _, window = key
            count = next(limit.count for limit in LIMITS[name] if limit.seconds == window)
            events = self._events.get(key)
            if events is not None and len(events) >= count:
                retry_after = max(retry_after, ceil(events[0] + window - now))
        return retry_after
