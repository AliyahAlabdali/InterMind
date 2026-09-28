"""Deterministic, testable policy for choosing which coverage target the adaptive interview
asks about next.

Pure functions over plain dicts (the interview graph's own state shape - see
``app.agents.interview_graph``), not the Pydantic ``CoverageTarget`` model: the graph's
``InterviewGraphState`` is a plain ``TypedDict`` of JSON-serialisable values (LangGraph
checkpoints it as-is), so this module works at that same level rather than requiring the graph
to reconstruct domain models on every node call.

This is the direct fix for the reported architecture issue: the interview used to walk a fixed,
pre-generated list of questions in a fixed order. Here, "what to ask next" is recomputed from
the *current* state (which targets are already assessed, which categories still have budget)
every time a main question is needed - never a static index into a list.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

#: How many MAIN questions (not follow-ups - those are uncapped by category, only by the
#: per-target follow-up cap in ``app.domain.evaluation``) the interview will ask from each
#: category before moving on, regardless of how many coverage targets that category has. Same
#: default numbers the old fixed-script planner used (4 + 4 + 2 = 10 total) - preserved as a
#: reasonable interview-length budget, but now enforced adaptively, one target at a time,
#: instead of being baked into which questions get pre-generated.
_CATEGORY_RANK = {"competency": 0, "technology": 1, "task": 2}


@dataclass(frozen=True)
class TargetSelectionPolicy:
    """How many main questions the interview may ask per category, and in total.

    ``total_budget`` (the sum) is also a safety bound on the whole interview, independent of
    per-category budgets - it guarantees the loop terminates even in a hypothetical
    misconfiguration where the per-category numbers don't add up the way a caller expects.
    """

    competency_budget: int = 4
    technology_budget: int = 4
    task_budget: int = 2

    @property
    def total_budget(self) -> int:
        return self.competency_budget + self.technology_budget + self.task_budget

    def budget_for(self, category: str) -> int:
        return {
            "competency": self.competency_budget,
            "technology": self.technology_budget,
            "task": self.task_budget,
        }.get(category, 0)


DEFAULT_POLICY = TargetSelectionPolicy()


def select_next_target(
    coverage_targets: list[dict],
    assessed_target_ids: list[str] | set[str],
    policy: TargetSelectionPolicy = DEFAULT_POLICY,
) -> dict | None:
    """Return the next coverage target to ask a main question about, or ``None`` to finish.

    ``coverage_targets`` items are dicts shaped like :class:`app.domain.interview_plan.
    CoverageTarget` (``id``/``target``/``category``/``requirement_level``/``priority``/
    ``grounding``). A target only ever appears in ``assessed_target_ids`` once its main
    question (and any follow-up on it) has fully resolved - see ``app.agents.interview_graph``
    - so this never re-selects a target still "in progress" (mid follow-up); the graph itself
    never calls this while a follow-up is outstanding.

    Selection order (global precedence, documented here as the one place this policy is
    decided): **required targets are prioritized over preferred ones ahead of everything
    else, regardless of category.** Within the same requirement tier, category order
    (competency, then technology, then task - preserving the order candidates have always been
    asked in) decides, and ``priority`` (JD order) breaks ties within that. Concretely: every
    unassessed, in-budget required target - in any category - is offered before any preferred
    target at all; only once every required target has been assessed or has run out of budget
    does a preferred target ever get selected. This matters because a category's budget is
    independent of the others (a preferred technology filling its own category's budget never
    "borrows" a slot from a different category's required targets), but the *global* interview
    could still end (see the ``total_budget`` safety cap below) before every category gets a
    turn - required-first ordering means that, if the interview has to stop early for any
    reason, the targets that actually mattered were the ones already covered.

    A category stops offering *preferred* candidates once ``assessed_target_ids`` already
    contains as many of its targets as its nominal budget allows - the interview moves on to
    another category instead of exhausting every possible preferred target in one. A category's
    *required* targets are never starved out this way: a real-run finding showed a JD with more
    required technologies (e.g. Python, RESTful APIs, FastAPI, PostgreSQL, Git) than
    ``technology_budget`` allows, which let the first four fill the category's nominal budget
    and silently close it before Git was ever offered as a candidate - even though Git was
    required and higher priority (lower ``required_rank``) than the preferred/task targets the
    selector fell through to instead. The category's *effective* cap is therefore
    ``max(nominal_budget, required_count_in_category)``: exactly the nominal budget whenever a
    category has no more required targets than that (the common case - no behaviour change),
    but large enough to admit every required target in a category otherwise, so required
    coverage is never bounded by a legacy per-category number tuned for the old fixed-script
    interview length. Preferred targets still only ever fill the *nominal* budget's worth of
    slots (see the effective-cap definition above) - they can never crowd out a required target
    in the same category, and once every required target's been assessed or the nominal budget
    is otherwise spent, no more preferred candidates are offered in that category.
    Returns ``None`` once every category is either out of (effective) budget or out of targets,
    or the overall ``total_budget`` safety cap is hit - that is what ends the interview: an
    outcome of the adaptive process, not a fixed count.
    """
    assessed = set(assessed_target_ids)
    if len(assessed) >= policy.total_budget:
        return None

    assessed_per_category = Counter(
        t["category"] for t in coverage_targets if t["id"] in assessed
    )
    required_per_category = Counter(
        t["category"] for t in coverage_targets if t["requirement_level"] == "required"
    )

    def effective_budget(category: str) -> int:
        return max(policy.budget_for(category), required_per_category[category])

    candidates = [
        t
        for t in coverage_targets
        if t["id"] not in assessed
        and assessed_per_category[t["category"]] < effective_budget(t["category"])
    ]
    if not candidates:
        return None

    def sort_key(t: dict) -> tuple[int, int, int]:
        required_rank = 0 if t["requirement_level"] == "required" else 1
        category_rank = _CATEGORY_RANK.get(t["category"], len(_CATEGORY_RANK))
        return (required_rank, category_rank, t["priority"])

    return min(candidates, key=sort_key)
