"""Unit tests for the deterministic, LLM-free target-selection policy.

This is the core fix for the reported "fixed 7-question script" architecture issue: which
coverage target the interview asks about next is recomputed from the current state (already-
assessed targets, remaining per-category budget) every time, never a static index into a
pre-generated list. See `app.services.target_selection` and `app.agents.interview_graph`.
"""

from __future__ import annotations

from app.services.target_selection import TargetSelectionPolicy, select_next_target


def _target(
    id: str,
    category: str,
    priority: int,
    requirement_level: str = "required",
    target: str | None = None,
) -> dict:
    return {
        "id": id,
        "target": target or id,
        "category": category,
        "requirement_level": requirement_level,
        "priority": priority,
        "grounding": "g",
    }


# --- required vs preferred, category ordering -------------------------------------------


def test_required_targets_are_prioritized_over_preferred_ones_in_the_same_category():
    targets = [
        _target("preferred-1", "technology", priority=0, requirement_level="preferred"),
        _target("required-1", "technology", priority=1, requirement_level="required"),
    ]
    selected = select_next_target(targets, assessed_target_ids=set())
    assert selected["id"] == "required-1"


def test_category_order_is_competency_then_technology_then_task():
    """Even when the underlying list is given in a different order, category order is always
    competency -> technology -> task - matching the order candidates have always been asked
    questions in, not whatever order the plan's coverage_targets happen to be listed."""
    targets = [
        _target("task-1", "task", priority=0),
        _target("technology-1", "technology", priority=0),
        _target("competency-1", "competency", priority=0),
    ]
    selected = select_next_target(targets, assessed_target_ids=set())
    assert selected["id"] == "competency-1"


def test_priority_breaks_ties_within_the_same_category_and_requirement_tier():
    targets = [
        _target("second", "technology", priority=1),
        _target("first", "technology", priority=0),
    ]
    selected = select_next_target(targets, assessed_target_ids=set())
    assert selected["id"] == "first"


# --- already-assessed targets are never reselected ----------------------------------------


def test_already_assessed_targets_are_never_reselected():
    targets = [
        _target("a", "competency", priority=0),
        _target("b", "competency", priority=1),
    ]
    selected = select_next_target(targets, assessed_target_ids={"a"})
    assert selected["id"] == "b"


def test_returns_none_once_every_target_is_assessed():
    targets = [_target("a", "competency", priority=0)]
    assert select_next_target(targets, assessed_target_ids={"a"}) is None


# --- per-category and total budgets ---------------------------------------------------------


def test_category_budget_stops_offering_that_category_even_with_unassessed_targets_left():
    targets = [
        _target("tech-1", "technology", priority=0),
        _target("tech-2", "technology", priority=1),
        _target("competency-1", "competency", priority=0),
    ]
    policy = TargetSelectionPolicy(competency_budget=4, technology_budget=1, task_budget=2)
    # tech-1 already used up the technology budget of 1 - tech-2 must never be offered, even
    # though it's a perfectly good, unassessed target - the interview moves to competency-1.
    selected = select_next_target(targets, assessed_target_ids={"tech-1"}, policy=policy)
    assert selected["id"] == "competency-1"


def test_total_budget_is_a_hard_safety_cap_on_the_whole_interview():
    targets = [_target("a", "competency", priority=0), _target("b", "technology", priority=0)]
    policy = TargetSelectionPolicy(competency_budget=1, technology_budget=1, task_budget=1)
    assert policy.total_budget == 3
    # Even if (hypothetically) more assessed ids exist than real targets, the cap still applies.
    assert select_next_target(targets, assessed_target_ids={"a", "b", "c"}, policy=policy) is None


def test_interview_finishes_once_every_required_target_is_covered_without_touching_preferred():
    """Test 12 (regression suite): a category budget that exactly matches its required-target
    count means the interview can finish having only ever covered required targets - a
    preferred target sitting right there, never assessed, is never selected once budget runs
    out, and the loop correctly reports nothing left to do."""
    targets = [
        _target("py", "technology", priority=0, requirement_level="required", target="Python"),
        _target(
            "excel", "technology", priority=1000, requirement_level="preferred", target="Excel"
        ),
    ]
    policy = TargetSelectionPolicy(competency_budget=0, technology_budget=1, task_budget=0)
    first = select_next_target(targets, assessed_target_ids=set(), policy=policy)
    assert first["id"] == "py"
    assert select_next_target(targets, assessed_target_ids={"py"}, policy=policy) is None


def test_default_policy_preserves_the_historical_ten_question_total_budget():
    """The old fixed-script planner asked at most 4 + 4 + 2 = 10 main questions - the default
    policy keeps that same practical bound, now enforced adaptively rather than by a
    pre-generated list length."""
    policy = TargetSelectionPolicy()
    assert policy.total_budget == 10


# --- Copilot review, SHOULD FIX 3: required has GLOBAL precedence over preferred ------------
#
# Required targets are prioritized ahead of preferred ones regardless of category - not just
# within the same category, as before. Category order (competency, technology, task) and JD
# priority still decide within the same requirement tier - see select_next_target's docstring
# for the full, documented policy.


def test_required_technology_is_selected_before_preferred_competency():
    """The clearest proof of global (not merely per-category) precedence: competency normally
    sorts before technology (category order), but a PREFERRED competency must not jump the
    queue ahead of a REQUIRED technology just because of that category order."""
    targets = [
        _target(
            "leadership", "competency", priority=0, requirement_level="preferred",
            target="Leadership",
        ),
        _target("python", "technology", priority=0, requirement_level="required", target="Python"),
    ]
    selected = select_next_target(targets, assessed_target_ids=set())
    assert selected["id"] == "python"


def test_required_task_is_selected_before_preferred_technology():
    """Task is always the last category by order, yet a REQUIRED task must still be offered
    before a PREFERRED technology, which would otherwise win purely on category order."""
    targets = [
        _target(
            "excel", "technology", priority=0, requirement_level="preferred", target="Excel"
        ),
        _target(
            "ship_it", "task", priority=0, requirement_level="required", target="Ship it.",
        ),
    ]
    selected = select_next_target(targets, assessed_target_ids=set())
    assert selected["id"] == "ship_it"


def test_required_targets_across_categories_are_never_stranded_behind_preferred_ones():
    """With every required target selected first (regardless of category) and only then
    preferred ones, a required target several categories "behind" a preferred one is never
    left uncovered if the interview has to stop early - it was already prioritized ahead of
    the preferred one, not stuck waiting for its own category's turn."""
    targets = [
        _target(
            "excel", "technology", priority=0, requirement_level="preferred", target="Excel"
        ),
        _target(
            "powerpoint", "technology", priority=1, requirement_level="preferred",
            target="PowerPoint",
        ),
        _target(
            "ship_it", "task", priority=0, requirement_level="required", target="Ship it.",
        ),
    ]
    # A budget that only allows ONE turn total, across all categories: if the interview stops
    # right there, the required task - not either preferred technology - must be what got
    # covered.
    policy = TargetSelectionPolicy(competency_budget=0, technology_budget=2, task_budget=1)
    first = select_next_target(targets, assessed_target_ids=set(), policy=policy)
    assert first["id"] == "ship_it"

    # Once the required target is covered, preferred ones are still reachable afterward - they
    # are deprioritized, never permanently dropped.
    second = select_next_target(targets, assessed_target_ids={"ship_it"}, policy=policy)
    assert second["id"] in ("excel", "powerpoint")


def test_all_required_targets_are_still_asked_in_category_order_among_themselves():
    """Global required-first precedence must not disturb the existing, documented category
    order *within* the required tier - this is a pure regression guard for the common case
    (every target required) that made up the bulk of the suite before this policy change."""
    targets = [
        _target("task-1", "task", priority=0, target="Task"),
        _target("technology-1", "technology", priority=0, target="Technology"),
        _target("competency-1", "competency", priority=0, target="Competency"),
    ]
    selected = select_next_target(targets, assessed_target_ids=set())
    assert selected["id"] == "competency-1"


def test_required_targets_are_never_starved_by_a_categorys_nominal_budget():
    """Real-run finding: a JD with more required technologies (Python, RESTful APIs, FastAPI,
    PostgreSQL, Git) than `technology_budget` (4, the default) let the first four fill the
    category's nominal budget and silently close it - Git was never even offered as a
    candidate, even though it was required, so the selector fell through to a lower-priority
    (task) category instead of ever reaching it. Every required target in a category must
    remain eligible regardless of the category's nominal budget."""
    targets = [
        _target("python", "technology", priority=0, target="Python"),
        _target("rest_apis", "technology", priority=1, target="RESTful APIs"),
        _target("fastapi", "technology", priority=2, target="FastAPI"),
        _target("postgres", "technology", priority=3, target="PostgreSQL"),
        _target("git", "technology", priority=4, target="Git"),
    ]
    # `task_budget=1` only exists so `total_budget` (5) doesn't itself become the binding
    # constraint here - the fix under test is the per-category cap, not the overall safety cap
    # (see `test_total_budget_is_a_hard_safety_cap_on_the_whole_interview` for that one).
    policy = TargetSelectionPolicy(competency_budget=0, technology_budget=4, task_budget=1)
    selected_order: list[str] = []
    assessed: set[str] = set()
    for _ in range(len(targets)):
        picked = select_next_target(targets, assessed_target_ids=assessed, policy=policy)
        assert picked is not None
        selected_order.append(picked["id"])
        assessed.add(picked["id"])

    # All five required technologies get a turn, not just the first four (the old nominal cap).
    assert set(selected_order) == {"python", "rest_apis", "fastapi", "postgres", "git"}
    assert select_next_target(targets, assessed_target_ids=assessed, policy=policy) is None


def test_preferred_targets_still_respect_the_nominal_category_budget_when_required_count_is_low():
    """Regression guard for the common case: when a category's required-target count is at or
    below its nominal budget (the typical shape), the effective cap must still equal the
    nominal budget - a preferred target must not gain extra room just because this fix exists."""
    targets = [
        _target("python", "technology", priority=0, target="Python"),
        _target(
            "docker", "technology", priority=1, requirement_level="preferred", target="Docker"
        ),
        _target("aws", "technology", priority=2, requirement_level="preferred", target="AWS"),
        _target(
            "async_python",
            "technology",
            priority=3,
            requirement_level="preferred",
            target="Async Python",
        ),
    ]
    policy = TargetSelectionPolicy(competency_budget=0, technology_budget=2, task_budget=0)
    first = select_next_target(targets, assessed_target_ids=set(), policy=policy)
    assert first["id"] == "python"
    second = select_next_target(targets, assessed_target_ids={"python"}, policy=policy)
    assert second["id"] == "docker"  # the one required target, then exactly one preferred slot
    third = select_next_target(targets, assessed_target_ids={"python", "docker"}, policy=policy)
    assert third is None  # nominal budget (2) is unchanged - "async_python" never offered


def test_real_interview_example_reaches_git_and_defers_the_redundant_task_targets():
    """Full reproduction of the reported real-run scenario: required Python/RESTful APIs/
    FastAPI/PostgreSQL/Git (technology) and two near-duplicate required task targets, plus
    preferred Docker/AWS. Before the category-budget fix, the interview asked all 4 technology
    slots (Python/RESTful APIs/FastAPI/PostgreSQL), found technology "closed", fell through to
    the two task duplicates, and finished having never reached Git. Git - a required technology
    - must now be selected ahead of the (also required, but lower category-priority) task
    duplicates, per the existing category-order rule, and the interview must still terminate."""
    targets = [
        _target("python", "technology", priority=0, target="Python"),
        _target("rest_apis", "technology", priority=1, target="RESTful APIs"),
        _target("fastapi", "technology", priority=2, target="FastAPI"),
        _target("postgres", "technology", priority=3, target="PostgreSQL"),
        _target("git", "technology", priority=4, target="Git"),
        _target(
            "backend_services",
            "task",
            priority=0,
            target="Design and implement backend services for AI-powered applications.",
        ),
        _target(
            "ml_rest_apis",
            "task",
            priority=1,
            target="Develop RESTful APIs that expose machine learning capabilities to client "
            "applications.",
        ),
        _target(
            "docker", "technology", priority=5, requirement_level="preferred", target="Docker"
        ),
        _target("aws", "technology", priority=6, requirement_level="preferred", target="AWS"),
    ]
    selected_order: list[str] = []
    assessed: set[str] = set()
    for _ in range(len(targets)):
        picked = select_next_target(targets, assessed_target_ids=assessed)
        if picked is None:
            break
        selected_order.append(picked["id"])
        assessed.add(picked["id"])

    assert "git" in selected_order
    git_index = selected_order.index("git")
    task_indices = [selected_order.index(t) for t in ("backend_services", "ml_rest_apis")]
    assert all(git_index < i for i in task_indices)
    # The interview still terminates - no infinite loop from lifting the category cap.
    assert select_next_target(targets, assessed_target_ids=set(assessed)) is None


def test_lifting_the_per_category_cap_still_terminates_when_required_count_is_large():
    """Safety-net regression for the category-budget fix: even a category with far more
    required targets than its nominal budget - and more required targets overall than
    `total_budget` - must still terminate via the unconditional total_budget safety cap. Lifting
    the per-category cap for required targets must never produce an unbounded interview."""
    targets = [
        _target(f"tech-{i}", "technology", priority=i, target=f"Tech {i}") for i in range(20)
    ]
    policy = TargetSelectionPolicy(competency_budget=0, technology_budget=4, task_budget=0)
    assessed: set[str] = set()
    turns = 0
    while True:
        picked = select_next_target(targets, assessed_target_ids=assessed, policy=policy)
        if picked is None:
            break
        assessed.add(picked["id"])
        turns += 1
        assert turns <= policy.total_budget  # never exceeds the hard safety cap
    assert turns == policy.total_budget


def test_adaptive_runtime_review_example_required_technologies_before_preferred():
    """The literal example from the adaptive-runtime review: REQUIRED Python/PostgreSQL/ML
    model integration must all be exhausted before PREFERRED Docker/AWS are ever selected,
    regardless of category - the selector must not choose a preferred technology merely
    because of category ordering while any required target remains unassessed."""
    targets = [
        _target(
            "docker", "technology", priority=0, requirement_level="preferred", target="Docker"
        ),
        _target("aws", "technology", priority=1, requirement_level="preferred", target="AWS"),
        _target(
            "python", "technology", priority=2, requirement_level="required", target="Python"
        ),
        _target(
            "postgres",
            "technology",
            priority=3,
            requirement_level="required",
            target="PostgreSQL",
        ),
        _target(
            "ml",
            "competency",
            priority=0,
            requirement_level="required",
            target="ML model integration",
        ),
    ]
    selected_order: list[str] = []
    assessed: set[str] = set()
    for _ in range(len(targets)):
        picked = select_next_target(targets, assessed_target_ids=assessed)
        assert picked is not None
        selected_order.append(picked["id"])
        assessed.add(picked["id"])

    # Every required target (regardless of category) is selected before either preferred one.
    required_ids = {"python", "postgres", "ml"}
    preferred_ids = {"docker", "aws"}
    last_required_index = max(selected_order.index(rid) for rid in required_ids)
    first_preferred_index = min(selected_order.index(pid) for pid in preferred_ids)
    assert last_required_index < first_preferred_index
