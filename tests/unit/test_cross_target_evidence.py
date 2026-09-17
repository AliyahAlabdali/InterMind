"""Unit tests for the deterministic, LLM-free cross-target evidence resolution.

Copilot review finding: a candidate answering a Python question who also volunteers real Java
experience had that evidence silently lost - the selector only ever looked at the target
actually asked about. See `app.services.cross_target_evidence` for the fix: a pure function
over already-produced, structured evidence items (never raw LLM output, never an LLM call of
its own), so `app.services.target_selection` stays exactly as LLM-free as before.
"""

from __future__ import annotations

from app.services.cross_target_evidence import resolve_cross_target_evidence


def _target(id: str, target: str, category: str = "technology") -> dict:
    return {
        "id": id,
        "target": target,
        "category": category,
        "requirement_level": "required",
        "priority": 0,
        "grounding": "g",
    }


COVERAGE_TARGETS = [
    _target("python", "Python"),
    _target("java", "Java"),
    _target("leadership", "Leadership", category="competency"),
]


def _evidence(target: str, evidence_type: str, note: str = "some note") -> dict:
    return {"target": target, "evidence_type": evidence_type, "note": note}


def _resolve(cross_target_evidence, *, current="python", assessed=(), hints=None):
    return resolve_cross_target_evidence(
        coverage_targets=COVERAGE_TARGETS,
        current_target_id=current,
        assessed_target_ids=list(assessed),
        cross_target_evidence=cross_target_evidence,
        existing_hints=hints or {},
    )


# --- 1: evidence for one target can affect another ------------------------------------------


def test_evidence_for_target_a_can_produce_a_signal_about_target_b():
    resolution = _resolve([_evidence("Java", "demonstrated", "built Java services")])
    assert resolution.newly_assessed_ids == ["java"]


# --- 2: strong evidence resolves the other target as sufficiently assessed ------------------


def test_demonstrated_evidence_resolves_the_other_target():
    resolution = _resolve([_evidence("Java", "demonstrated", "built and shipped Java services")])
    assert resolution.newly_assessed_ids == ["java"]
    assert len(resolution.history_entries) == 1
    entry = resolution.history_entries[0]
    assert entry["root_question_id"] == "java"
    assert entry["question_id"] == "java"
    assert entry["evaluation"]["decision"] == "advance"
    assert entry["evaluation"]["evidence_type"] == "demonstrated"
    assert entry["evaluation"]["score"] >= 0.8
    assert "java" not in resolution.updated_hints


def test_explicit_lack_evidence_also_resolves_the_other_target():
    """Explicit lack is just as conclusive as demonstrated evidence - nothing more to probe,
    whether it came from a direct question or incidentally from a different one."""
    resolution = _resolve([_evidence("Java", "explicit_lack", "never touched Java")])
    assert resolution.newly_assessed_ids == ["java"]
    entry = resolution.history_entries[0]
    assert entry["evaluation"]["decision"] == "advance"
    assert entry["evaluation"]["evidence_type"] == "explicit_lack"
    assert entry["evaluation"]["score"] < 0.35


# --- 3: a casual mention must not incorrectly mark the target fully assessed ----------------


def test_casual_mention_is_recorded_as_a_hint_not_a_resolution():
    resolution = _resolve([_evidence("Java", "claimed_unverified", "also used Java a bit")])
    assert resolution.newly_assessed_ids == []
    assert resolution.history_entries == []
    assert resolution.updated_hints["java"] == {
        "evidence_type": "claimed_unverified",
        "note": "also used Java a bit",
    }


def test_partial_and_contradictory_mentions_are_also_only_hints():
    for evidence_type in ("partial", "contradictory", "insufficient"):
        resolution = _resolve([_evidence("Java", evidence_type)])
        assert resolution.newly_assessed_ids == [], evidence_type
        assert resolution.history_entries == [], evidence_type
        assert "java" in resolution.updated_hints, evidence_type


# --- 4: explicit lack of the CURRENT target must never invent evidence for another ----------


def test_current_target_itself_is_never_treated_as_cross_target_evidence():
    """Evidence about the target actually being asked about (however it's phrased) is the
    primary evaluation's job - it must never be reinterpreted as a signal about some other
    target, even if it happens to name-match by accident."""
    resolution = _resolve([_evidence("Python", "explicit_lack", "no Python experience")])
    assert resolution.newly_assessed_ids == []
    assert resolution.history_entries == []
    assert resolution.updated_hints == {}


def test_no_cross_target_evidence_means_no_resolution_at_all():
    resolution = _resolve([])
    assert resolution.newly_assessed_ids == []
    assert resolution.history_entries == []
    assert resolution.updated_hints == {}


# --- already-assessed / unknown / duplicate targets are handled safely ----------------------


def test_already_assessed_target_is_never_re_resolved():
    resolution = _resolve(
        [_evidence("Java", "demonstrated")], assessed=["java"]
    )
    assert resolution.newly_assessed_ids == []
    assert resolution.history_entries == []


def test_unknown_target_name_is_ignored_not_crashed():
    resolution = _resolve([_evidence("Rust", "demonstrated")])
    assert resolution.newly_assessed_ids == []
    assert resolution.history_entries == []


def test_duplicate_conclusive_evidence_within_one_turn_resolves_only_once():
    resolution = _resolve(
        [
            _evidence("Java", "demonstrated", "first mention"),
            _evidence("Java", "demonstrated", "second mention"),
        ]
    )
    assert resolution.newly_assessed_ids == ["java"]
    assert len(resolution.history_entries) == 1


def test_a_later_conclusive_resolution_clears_an_earlier_hint():
    resolution = _resolve(
        [_evidence("Java", "demonstrated", "built Java services")],
        hints={"java": {"evidence_type": "claimed_unverified", "note": "earlier mention"}},
    )
    assert resolution.newly_assessed_ids == ["java"]
    assert "java" not in resolution.updated_hints


def test_existing_hints_for_other_targets_are_preserved():
    resolution = _resolve(
        [_evidence("Java", "demonstrated")],
        hints={"leadership": {"evidence_type": "claimed_unverified", "note": "led a project"}},
    )
    assert resolution.updated_hints["leadership"] == {
        "evidence_type": "claimed_unverified",
        "note": "led a project",
    }


# --- 5: resolution is a pure, deterministic function ----------------------------------------


def test_resolution_is_deterministic_across_repeated_calls():
    args = dict(cross_target_evidence=[_evidence("Java", "demonstrated", "built Java services")])
    first = _resolve(**args)
    second = _resolve(**args)
    assert first.newly_assessed_ids == second.newly_assessed_ids
    assert first.history_entries == second.history_entries
    assert first.updated_hints == second.updated_hints
