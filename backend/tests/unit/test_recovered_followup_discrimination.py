"""Offline regression checks for the separately recovered v1.1 metrics."""

import pytest

from evals.recovery_v11 import followup_discrimination as recovery

pytestmark = pytest.mark.private_history


def test_raw_confusion_uses_human_positive_class():
    rows = [
        ("FOLLOW_UP_WARRANTED", "follow_up"),
        ("FOLLOW_UP_WARRANTED", "advance"),
        ("NO_FOLLOW_UP_WARRANTED", "follow_up"),
        ("NO_FOLLOW_UP_WARRANTED", "advance"),
        ("AMBIGUOUS", "follow_up"),
    ]
    result = recovery.confusion(rows)
    assert {key: result[key] for key in ("tp", "fp", "fn", "tn")} == {
        "tp": 1, "fp": 1, "fn": 1, "tn": 1,
    }
    assert result["precision"] == result["recall"] == result["f1"] == 0.5


def test_frozen_recovery_metrics_are_routed_and_complete():
    followups, personas, labels, manifest = recovery.verify_inputs()
    result = recovery.build_metrics(
        followups, personas, labels, manifest, bootstrap_samples=100
    )
    routed = result["follow_up"]["routed_metrics"]
    raw = result["follow_up"]["raw_model_diagnostic"]
    assert routed["n_total"] == routed["n_primary"] == 90
    assert routed["n_bootstrap_clusters"] == 38
    assert (routed["tp"], routed["fp"], routed["fn"], routed["tn"]) == (27, 3, 4, 56)
    assert (raw["tp"], raw["fp"], raw["fn"], raw["tn"]) == (24, 0, 7, 59)
    overrides = result["follow_up"]["routing_overrides"]
    assert len(overrides) == 6
    assert all(row["raw_model_decision"] == "advance"
               and row["final_route"] == "follow_up" for row in overrides)
    assert result["discrimination"]["n_personas"] == 15
    assert result["discrimination"]["ordered_jobs"] == 5
    assert result["discrimination"]["gate_passed"] is True
    assert len(result["discrimination"]["per_job"]) == 5


def test_changed_prior_artifact_hash_blocks_recovery(monkeypatch):
    changed = dict(recovery.PRIOR_SHA256)
    first = next(iter(changed))
    changed[first] = "0" * 64
    monkeypatch.setattr(recovery, "PRIOR_SHA256", changed)
    with pytest.raises(ValueError, match="Prior v1.1 result changed"):
        recovery.verify_inputs()


def test_duplicate_case_id_blocks_recovery(monkeypatch):
    original_progress = recovery.progress

    def duplicate_progress():
        rows = original_progress()
        rows["followup"][1] = rows["followup"][0]
        return rows

    monkeypatch.setattr(recovery, "progress", duplicate_progress)
    with pytest.raises(ValueError, match="Recovered follow-up case IDs changed"):
        recovery.verify_inputs()
