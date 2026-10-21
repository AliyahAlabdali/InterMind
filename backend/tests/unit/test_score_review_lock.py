"""Offline validation and write-once locking of the v1.1a score review."""

from __future__ import annotations

from copy import deepcopy

import pytest

from evals.recovery_v11 import score_review_lock as review

pytestmark = pytest.mark.private_history


def _rows():
    return review._read_csv(review.RELEASED), review._read_csv(review.REVIEW)


def test_completed_review_and_source_locks_validate():
    verdicts, omissions = review.validate()
    assert sum(verdicts.values()) == sum(omissions.values()) == 45
    assert verdicts == {"DEFENSIBLE": 44, "NOT_DEFENSIBLE": 1, "UNCLEAR": 0}
    assert omissions == {"YES": 6, "NO": 39, "UNCLEAR": 0}


def test_missing_duplicate_and_reordered_ids_rejected():
    original, completed = _rows()
    with pytest.raises(ValueError, match="Expected 45"):
        review.validate_rows(original, completed[:-1])
    changed = deepcopy(completed)
    changed[0]["score_review_id"] = changed[1]["score_review_id"]
    with pytest.raises(ValueError, match="Duplicate"):
        review.validate_rows(original, changed)
    changed = deepcopy(completed)
    changed[0]["score_review_id"] = "unknown"
    with pytest.raises(ValueError, match="Missing or unknown"):
        review.validate_rows(original, changed)
    changed = deepcopy(completed)
    changed[0], changed[1] = changed[1], changed[0]
    with pytest.raises(ValueError, match="row order"):
        review.validate_rows(original, changed)


def test_changed_source_and_invalid_human_fields_rejected():
    original, completed = _rows()
    changed = deepcopy(completed)
    changed[0]["score"] += "0"
    with pytest.raises(ValueError, match="source field score changed"):
        review.validate_rows(original, changed)
    changed = deepcopy(completed)
    changed[0]["full_candidate_answer"] += " extra"
    with pytest.raises(ValueError, match="source field full_candidate_answer changed"):
        review.validate_rows(original, changed)
    changed = deepcopy(completed)
    changed[0]["verdict"] = "MAYBE"
    with pytest.raises(ValueError, match="invalid verdict"):
        review.validate_rows(original, changed)
    changed = deepcopy(completed)
    changed[0]["material_omission"] = "MAYBE"
    with pytest.raises(ValueError, match="invalid material_omission"):
        review.validate_rows(original, changed)


def test_missing_explanations_rejected():
    original, completed = _rows()
    changed = deepcopy(completed)
    changed[0]["verdict"] = "NOT_DEFENSIBLE"
    changed[0]["note"] = " "
    with pytest.raises(ValueError, match="missing explanatory note"):
        review.validate_rows(original, changed)
    changed = deepcopy(completed)
    changed[0]["material_omission"] = "UNCLEAR"
    changed[0]["omission_detail"] = " "
    with pytest.raises(ValueError, match="missing omission_detail"):
        review.validate_rows(original, changed)


def test_successful_lock_and_overwrite_refused(tmp_path):
    lock_path = tmp_path / "COMPLETED_SCORE_REVIEW.lock.json"
    saved = review.freeze(lock_path=lock_path, protect=False)
    assert saved["validated_assessments"] == 45
    assert saved["completed_review_sha256"] == review.sha(review.REVIEW)
    assert saved["release_lock_sha256"] == review.sha(review.RELEASE_LOCK)
    assert saved["score_validity_metrics_calculated"] is False
    assert lock_path.exists()
    with pytest.raises(FileExistsError, match="already exists"):
        review.freeze(lock_path=lock_path, protect=False)
