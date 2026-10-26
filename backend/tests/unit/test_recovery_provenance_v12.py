"""Historical provenance checks are independent of current runtime behavior."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from app.domain.evaluation import AnswerEvidenceType, evidence_label
from evals.recovery_v11 import audit, latency
from evals.recovery_v11 import provenance_v12 as provenance

pytestmark = pytest.mark.private_history


def test_authentic_historical_source_matches_frozen_v11():
    result = provenance.verify_historical_provenance()
    assert result["version"] == "1.2-historical-provenance"
    assert result["locked_files_verified"] == 37
    assert result["historical_app_files_verified"] == 10
    assert result["historical_eval_files_verified"] == 2
    assert result["manifest_source_files_verified"] == 10
    assert result["historical_manifest_sha256"] == provenance.MANIFEST_SHA256


def test_historical_gate_rejects_modified_evaluation_source_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    snapshot = tmp_path / "historical_source_v1_1"
    shutil.copytree(provenance.SNAPSHOT, snapshot)
    source = snapshot / "evals/recovery_v11/latency.py"
    source.write_bytes(source.read_bytes() + b"# tampered\r\n")

    def verify_modified_snapshot():
        return provenance.verify_historical_provenance(snapshot_root=snapshot)

    monkeypatch.setattr(latency, "verify_historical_provenance", verify_modified_snapshot)
    monkeypatch.setattr(audit, "verify_historical_provenance", verify_modified_snapshot)
    error = "Historical recovery source changed: recovery_v11/latency.py"
    with pytest.raises(ValueError, match=error):
        latency.require_lock()
    with pytest.raises(ValueError, match=error):
        audit.audit()


def test_modified_historical_source_and_line_endings_fail(tmp_path: Path):
    snapshot = tmp_path / "historical_source_v1_1"
    shutil.copytree(provenance.SNAPSHOT, snapshot)
    source = snapshot / "app/llm/openai_client.py"
    original = source.read_bytes()
    assert b"\r\n" in original
    source.write_bytes(original.replace(b"\r\n", b"\n"))
    with pytest.raises(ValueError, match="Historical recovery source changed:.*openai_client.py"):
        provenance.verify_historical_provenance(snapshot_root=snapshot)
    source.write_bytes(original + b"# tampered\r\n")
    with pytest.raises(ValueError, match="Historical recovery source changed:.*openai_client.py"):
        provenance.verify_historical_provenance(snapshot_root=snapshot)


def test_modified_manifest_and_lock_fail_before_source_checks(tmp_path: Path):
    manifest_path = tmp_path / "RECOVERY_MANIFEST_v1.1.json"
    manifest = json.loads(provenance.MANIFEST.read_text(encoding="utf-8"))
    manifest["version"] = "1.1-modified"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Historical recovery manifest changed"):
        provenance.verify_historical_provenance(manifest_path=manifest_path)

    lock_path = tmp_path / "PROTOCOL_v1.1.lock.json"
    lock = json.loads(provenance.LOCK.read_text(encoding="utf-8"))
    lock["sha256"]["../app/llm/openai_client.py"] = "0" * 64
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises(ValueError, match="Historical recovery protocol lock changed"):
        provenance.verify_historical_provenance(lock_path=lock_path)


def test_modified_frozen_evaluation_input_still_fails(tmp_path: Path):
    lock = json.loads(provenance.LOCK.read_text(encoding="utf-8"))
    for relative in lock["sha256"]:
        if relative.startswith("../app/"):
            continue
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((provenance.EVAL_ROOT / relative).read_bytes())
    target = tmp_path / "labels/followup_blind.frozen.csv"
    target.write_bytes(target.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="Historical recovery source changed:.*followup_blind"):
        provenance.verify_historical_provenance(eval_root=tmp_path)


def test_current_runtime_drift_does_not_rewrite_historical_provenance():
    current = Path(__file__).resolve().parents[2] / "app/llm/openai_client.py"
    historical = provenance.SNAPSHOT / "app/llm/openai_client.py"
    assert hashlib.sha256(current.read_bytes()).hexdigest() != hashlib.sha256(
        historical.read_bytes()
    ).hexdigest()
    before = historical.read_bytes()
    provenance.verify_historical_provenance()
    assert historical.read_bytes() == before


def test_current_runtime_evidence_semantics_are_checked_independently():
    """A current-runtime behavior check does not depend on historical source locks."""
    assert evidence_label(AnswerEvidenceType.EXPLICIT_LACK, 0.1) == "No evidence"
    assert evidence_label(AnswerEvidenceType.CLAIMED_UNVERIFIED, 0.1) == "Unverified claim"
    assert provenance.verify_historical_provenance()["locked_files_verified"] == 37
