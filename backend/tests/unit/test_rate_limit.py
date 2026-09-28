"""Unit tests for the process-local rolling-window limiter.

Three properties matter, and each is exercised directly rather than through a route: budgets are
consumed atomically, the window really rolls, and the table of counters stays bounded no matter
what identities a caller invents. The clock is injected, so nothing here sleeps.

Several tests read ``limiter._events`` on purpose. Bounded memory is a property of that
dictionary rather than of any response, so there is nothing observable from outside to assert
on - the alternative would be to assert nothing and simply hope.
"""

from __future__ import annotations

import threading
from collections import deque

import pytest

from app.core.limits import LIMITS, Limit
from app.core.rate_limit import MAX_TRACKED_KEYS, RateLimiter, RateLimitExceeded


class FakeClock:
    """A monotonic clock the test advances by hand."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def limiter(clock: FakeClock) -> RateLimiter:
    return RateLimiter(clock=clock)


def _budget(name: str) -> Limit:
    """The single configured window for ``name``, for buckets that have exactly one."""
    limits = LIMITS[name]
    assert len(limits) == 1, f"{name} has more than one window; pick one explicitly"
    return limits[0]


# --- the budget itself ------------------------------------------------------------------------


def test_admits_up_to_the_configured_count_then_refuses(limiter):
    budget = _budget("report_recruiter")
    for _ in range(budget.count):
        limiter.check(("report_recruiter", "recruiter-a"))

    with pytest.raises(RateLimitExceeded):
        limiter.check(("report_recruiter", "recruiter-a"))


def test_identities_do_not_share_a_budget(limiter):
    budget = _budget("report_recruiter")
    for _ in range(budget.count):
        limiter.check(("report_recruiter", "recruiter-a"))

    # A different caller is unaffected by the first one's exhausted budget.
    limiter.check(("report_recruiter", "recruiter-b"))


def test_the_window_rolls_rather_than_resetting_on_a_boundary(limiter, clock):
    """Admissions come back one at a time, as each individual event ages out - not all at once
    on a boundary, which is what a fixed bucket would do and what lets a caller spend two full
    budgets back to back across one."""
    budget = _budget("report_recruiter")
    start = clock.now
    # Spaced a second apart, so they do not all expire at the same instant.
    for _ in range(budget.count):
        limiter.check(("report_recruiter", "recruiter-a"))
        clock.advance(1)

    # Budget spent, and every event still inside its window.
    with pytest.raises(RateLimitExceeded):
        limiter.check(("report_recruiter", "recruiter-a"))

    # Advance to exactly the moment the *oldest* event ages out, and no further.
    clock.now = start + budget.seconds
    limiter.check(("report_recruiter", "recruiter-a"))

    # Precisely one admission was returned: the second-oldest event has not expired yet.
    with pytest.raises(RateLimitExceeded):
        limiter.check(("report_recruiter", "recruiter-a"))


def test_retry_after_is_positive_and_within_the_window(limiter):
    budget = _budget("report_recruiter")
    for _ in range(budget.count):
        limiter.check(("report_recruiter", "recruiter-a"))

    with pytest.raises(RateLimitExceeded) as excinfo:
        limiter.check(("report_recruiter", "recruiter-a"))

    assert 0 < excinfo.value.retry_after <= budget.seconds


def test_the_exception_carries_no_identity(limiter):
    """Its message reaches a response body, so it must not describe who was limited."""
    budget = _budget("report_recruiter")
    for _ in range(budget.count):
        limiter.check(("report_recruiter", "recruiter-secret-id"))

    with pytest.raises(RateLimitExceeded) as excinfo:
        limiter.check(("report_recruiter", "recruiter-secret-id"))

    assert "recruiter-secret-id" not in str(excinfo.value)
    assert "report_recruiter" not in str(excinfo.value)


# --- atomicity --------------------------------------------------------------------------------


def test_a_refused_call_consumes_nothing(limiter, clock):
    """All-or-nothing: a request refused by its second budget must not have spent its first."""
    for _ in range(LIMITS["job_global"][0].count):
        limiter.check(("job_global", "all"))

    # A fresh identity against an exhausted global ceiling: refused.
    with pytest.raises(RateLimitExceeded):
        limiter.check(("job_recruiter", "recruiter-c"), ("job_global", "all"))

    # That identity's own budget was not charged, so it still has its full allowance - proven by
    # draining it exactly ``count`` times before it refuses.
    for _ in range(LIMITS["job_recruiter"][0].count):
        limiter.check(("job_recruiter", "recruiter-c"))
    with pytest.raises(RateLimitExceeded):
        limiter.check(("job_recruiter", "recruiter-c"))


def test_naming_one_bucket_twice_spends_it_once(limiter):
    """De-duplication: repeating a bucket must not charge it twice."""
    budget = _budget("report_recruiter")
    for _ in range(budget.count):
        limiter.check(("report_recruiter", "recruiter-a"), ("report_recruiter", "recruiter-a"))

    with pytest.raises(RateLimitExceeded):
        limiter.check(("report_recruiter", "recruiter-a"))


def test_an_unknown_bucket_is_loud_rather_than_unlimited(limiter):
    """A typo in a bucket name must never silently mean "no limit"."""
    with pytest.raises(KeyError):
        limiter.check(("not_a_configured_bucket", "whoever"))


# --- bounded memory ---------------------------------------------------------------------------


def test_cycling_identities_cannot_grow_the_table_without_bound(limiter):
    """The core anti-abuse property: a caller cycling identities is stopped by the global
    ceiling *before* a new per-identity key is recorded, so the table stops growing even though
    every request arrives under a previously unseen identity."""
    attempts = 5_000
    for attempt in range(attempts):
        try:
            limiter.check(("job_recruiter", f"recruiter-{attempt}"), ("job_global", "all"))
        except RateLimitExceeded:
            break
    else:  # pragma: no cover - would mean the global ceiling never engaged
        pytest.fail("the global ceiling never refused a request")

    # One key per (bucket, identity, window), bounded by the global budget rather than by how
    # many identities were tried.
    ceiling = LIMITS["job_global"][0].count * len(LIMITS["job_recruiter"]) + len(
        LIMITS["job_global"]
    )
    assert len(limiter._events) <= ceiling
    assert len(limiter._events) < attempts


def test_expired_keys_are_removed_entirely(limiter, clock):
    limiter.check(("report_recruiter", "recruiter-a"))
    assert limiter._events

    clock.advance(_budget("report_recruiter").seconds + 1)
    limiter.check(("report_recruiter", "recruiter-b"))

    # The first identity's key is gone, not merely emptied.
    assert all(key[1] != "recruiter-a" for key in limiter._events)


def test_the_backstop_refuses_new_identities_but_not_tracked_ones(limiter, clock):
    """Defence in depth beneath the global ceilings: were a bucket ever added with no global
    companion, the table still could not grow past MAX_TRACKED_KEYS. A caller already being
    tracked keeps working, so the backstop closes the door only on the novel caller.

    The table is filled directly because reaching the backstop through ``check`` would require
    exactly the misconfiguration this guards against.
    """
    window = _budget("report_recruiter").seconds
    for index in range(MAX_TRACKED_KEYS):
        limiter._events[("report_recruiter", f"r{index}", window)] = deque([clock.now])

    with pytest.raises(RateLimitExceeded):
        limiter.check(("report_recruiter", "a-brand-new-recruiter"))

    # Already tracked, and within its own budget: still admitted.
    limiter.check(("report_recruiter", "r0"))


# --- concurrency ------------------------------------------------------------------------------


def test_concurrent_callers_never_exceed_the_budget():
    """Read-modify-write on the counters must be indivisible: with many threads racing on one
    budget, the number admitted must equal that budget exactly - never more.

    Uses the real clock; the assertion is about how many callers got through, not about time.
    """
    limiter = RateLimiter()
    budget = _budget("report_recruiter")
    attempts = budget.count * 8
    admitted: list[int] = []
    tally = threading.Lock()
    start = threading.Barrier(attempts)

    def attempt() -> None:
        start.wait()
        try:
            limiter.check(("report_recruiter", "recruiter-a"))
        except RateLimitExceeded:
            return
        with tally:
            admitted.append(1)

    threads = [threading.Thread(target=attempt) for _ in range(attempts)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(admitted) == budget.count
