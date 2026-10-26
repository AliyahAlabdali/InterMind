"""Public-checkout tests for the private historical bundle verifier."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from evals.private_history import (
    PrivateArtifactError,
    required_artifacts,
    required_private_inputs,
    verify_bundle,
    verify_private_inputs,
)


def test_published_locks_require_the_original_nineteen_files():
    expected = required_artifacts()
    counts = {part: sum(path.parts[0] == part for path in expected) for part in {
        "20261011T214346Z-pilot",
        "20261011T223751Z-final",
        "20261011T231332Z-v11-preflight",
        "20261011T231631Z-v11-latency",
    }}
    assert counts == {
        "20261011T214346Z-pilot": 9,
        "20261011T223751Z-final": 2,
        "20261011T231332Z-v11-preflight": 4,
        "20261011T231631Z-v11-latency": 4,
    }
    assert len(expected) == 19


def test_published_locks_require_eight_answer_bearing_review_inputs():
    expected = required_private_inputs()
    assert len(expected) == 8
    assert Path("labels/followup_blind.frozen.csv") in expected
    assert Path(
        "recovery_v11/human_review/intermind_final_user_adjudicated_245.csv"
    ) in expected


def test_raw_bytes_pass_and_line_ending_change_fails(tmp_path: Path):
    path = tmp_path / "run" / "progress.jsonl"
    path.parent.mkdir()
    original = b'{"status":"incomplete"}\r\n'
    path.write_bytes(original)
    expected = {Path("run/progress.jsonl"): hashlib.sha256(original).hexdigest()}
    assert verify_bundle(tmp_path, expected) == 1

    path.write_bytes(original.replace(b"\r\n", b"\n"))
    with pytest.raises(PrivateArtifactError, match="Altered private historical artifact"):
        verify_bundle(tmp_path, expected)


def test_missing_and_extra_private_files_fail_clearly(tmp_path: Path):
    path = tmp_path / "run" / "progress.jsonl"
    expected = {Path("run/progress.jsonl"): hashlib.sha256(b"locked").hexdigest()}
    with pytest.raises(PrivateArtifactError, match="Missing private historical artifact"):
        verify_bundle(tmp_path, expected)

    path.parent.mkdir()
    path.write_bytes(b"locked")
    (path.parent / "unexpected.json").write_bytes(b"extra")
    with pytest.raises(PrivateArtifactError, match="file set changed"):
        verify_bundle(tmp_path, expected)


def test_missing_or_altered_private_review_input_fails(tmp_path: Path):
    relative = Path("labels/followup_blind.frozen.csv")
    expected = {relative: hashlib.sha256(b"original\r\n").hexdigest()}
    with pytest.raises(PrivateArtifactError, match="Missing private historical artifact"):
        verify_private_inputs(tmp_path, expected)
    path = tmp_path / relative
    path.parent.mkdir()
    path.write_bytes(b"original\n")
    with pytest.raises(PrivateArtifactError, match="Altered private historical artifact"):
        verify_private_inputs(tmp_path, expected)
