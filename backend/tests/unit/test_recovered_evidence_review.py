"""Offline checks for write-once recovery evidence review freezing."""

import csv
import json

import pytest

from evals.recovery_v11 import evidence_review as review


@pytest.fixture
def review_sheet(tmp_path, monkeypatch):
    expected = [{
        "evidence_id": "ev-example", "evidence_string": "A documented action",
        "target_question": "What happened?", "target_answer": "A documented action.",
        "full_interview_context": "[1] Q: What happened?\nA: A documented action.",
        "source_answer_index": "", "verdict": "", "note": "",
    }]
    path = tmp_path / "blind.csv"
    monkeypatch.setattr(review, "REVIEW", path)
    monkeypatch.setattr(review, "FROZEN", tmp_path / "frozen")
    monkeypatch.setattr(review, "require_lock", lambda: None)
    monkeypatch.setattr(review, "audit", lambda: ({}, expected))

    def write(row):
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(expected[0]))
            writer.writeheader()
            writer.writerow(row)

    return expected[0], path, write


def test_freeze_preserves_completed_review_and_hash(review_sheet):
    original, path, write = review_sheet
    write({**original, "source_answer_index": "1", "verdict": "supported"})
    destination = review.freeze_review()
    frozen = destination / "evidence_source_review_frozen.csv"
    lock = json.loads((destination / "evidence_source_review.lock.json").read_text())
    assert frozen.read_bytes() == path.read_bytes()
    assert lock["sha256"][frozen.name] == review.sha(frozen)
    assert lock["reviewed_rows"] == 1
    with pytest.raises(FileExistsError):
        review.freeze_review()


@pytest.mark.parametrize("changes", [
    {"verdict": ""}, {"verdict": "unknown"},
    {"source_answer_index": ""}, {"source_answer_index": "11"},
    {"source_answer_index": "1;1"}, {"evidence_id": "wrong"},
])
def test_rejects_incomplete_or_changed_review(review_sheet, changes):
    original, _, write = review_sheet
    row = {**original, "source_answer_index": "1", "verdict": "supported", **changes}
    write(row)
    with pytest.raises(ValueError):
        review.validate_review()


def test_requires_explanation_for_unclear(review_sheet):
    original, _, write = review_sheet
    write({**original, "verdict": "cannot_tell"})
    with pytest.raises(ValueError, match="Explanation required"):
        review.validate_review()
