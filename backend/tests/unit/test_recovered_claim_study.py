"""Offline regression checks for the v1.1 source-locked claim review adapter."""

from __future__ import annotations

import csv
import json

import pytest

from evals.claim_validity import study
from evals.recovery_v11 import claim_study

pytestmark = pytest.mark.private_history


@pytest.fixture(scope="module")
def recovered():
    return claim_study.validated_inventory()


def test_recovered_inventory_uses_frozen_sample_and_report_hashes(recovered):
    inventory, source = recovered
    assert source["source_run_status"] == "incomplete"
    assert len(source["persona_report_sha256"]) == 15
    assert len(set(source["persona_report_sha256"].values())) == 15
    assert len(inventory["claims"]) == 245
    assert len({item["claim_id"] for item in inventory["claims"]}) == 245
    assert len(inventory["scores"]) == 45
    assert len(inventory["calculation_checks"]) == 15
    sample = study.selected_targets()
    assert all(len(targets) == 3 for targets in sample.values())


def test_blind_sheet_and_stage_gate(tmp_path, monkeypatch, recovered):
    monkeypatch.setattr(claim_study, "validated_inventory", lambda: recovered)
    out_dir = tmp_path / "review"
    claim_study.prepare(out_dir)
    assert not (out_dir / "scores_initial.csv").exists()
    assert not (out_dir / "claims_ai.csv").exists()
    assert not (out_dir / "claims_final.csv").exists()
    rows = study.read_csv(out_dir / "claims_initial_blind.csv", study.CLAIM_FIELDS)
    assert len(rows) == 245
    assert all(not row["verdict"] and not row["note"] for row in rows)
    assert all("strengths" not in row["report_location"]
               and "weaknesses" not in row["report_location"] for row in rows)
    assert not {"persona_tier", "score", "recommendation", "automatic_verdict",
                "ai_suggestion"}.intersection(study.CLAIM_FIELDS)
    assert claim_study.verify(out_dir)["human_verdicts_entered"] == 0
    with pytest.raises(ValueError, match="Missing or invalid initial claim verdict"):
        claim_study.freeze_claims(out_dir)
    assert not (out_dir / "scores_initial.csv").exists()


def test_changed_source_lock_and_duplicate_claim_block_review(tmp_path, monkeypatch, recovered):
    monkeypatch.setattr(claim_study, "validated_inventory", lambda: recovered)
    out_dir = tmp_path / "review"
    claim_study.prepare(out_dir)
    rows = study.read_csv(out_dir / "claims_initial_blind.csv", study.CLAIM_FIELDS)
    rows[1]["claim_id"] = rows[0]["claim_id"]
    study.write_csv(out_dir / "claims_initial_blind.csv", study.CLAIM_FIELDS, rows)
    with pytest.raises(ValueError, match="duplicate"):
        claim_study.verify(out_dir)
    source_path = out_dir / "source.lock.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["n_claims"] = 244
    source_path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(ValueError, match="source lock"):
        claim_study.verify(out_dir)


def test_changed_claim_context_blocks_freeze(tmp_path, monkeypatch, recovered):
    monkeypatch.setattr(claim_study, "validated_inventory", lambda: recovered)
    out_dir = tmp_path / "review"
    claim_study.prepare(out_dir)
    path = out_dir / "claims_initial_blind.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["claim_text"] = "Changed claim"
    study.write_csv(path, study.CLAIM_FIELDS, rows)
    with pytest.raises(ValueError, match="Review context changed"):
        claim_study.freeze_claims(out_dir)
    assert not (out_dir / "claims_initial.lock.json").exists()
