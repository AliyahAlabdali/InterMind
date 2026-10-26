"""Offline guards for the retrospective v1.1a score-sheet release."""

from __future__ import annotations

from copy import deepcopy

import pytest

from evals.recovery_v11 import claim_score_addendum as addendum

pytestmark = pytest.mark.private_history


@pytest.fixture(scope="module")
def checked():
    return addendum.preflight()


def test_source_locked_claims_and_scores_validate(checked):
    inventory, adopted, categories = checked
    assert len(adopted) == len(inventory["claims"]) == 245
    assert len(inventory["scores"]) == len(categories) == 45
    assert len({item["report_id"] for item in inventory["scores"]}) == 15
    assert set(categories.values()) == {"competency", "technology", "task"}


def test_invalid_or_duplicated_adopted_judgment_rejected(checked):
    inventory, adopted, _ = checked
    rows = deepcopy(adopted)
    rows[0]["final_human_verdict"] = "MAYBE"
    with pytest.raises(ValueError, match="invalid final human"):
        addendum.validate_adopted(rows, inventory["claims"])
    rows = deepcopy(adopted)
    rows[0]["claim_id"] = rows[1]["claim_id"]
    with pytest.raises(ValueError, match="duplicate"):
        addendum.validate_adopted(rows, inventory["claims"])
    rows = deepcopy(adopted)
    rows[0]["full_candidate_answer"] += " changed"
    with pytest.raises(ValueError, match="candidate answer changed"):
        addendum.validate_adopted(rows, inventory["claims"])


def test_score_source_mismatch_rejected(checked):
    inventory, _, _ = checked
    rows = deepcopy(inventory["scores"])
    rows[0]["score_review_id"] = rows[1]["score_review_id"]
    with pytest.raises(ValueError, match="45 frozen preselected IDs"):
        addendum.validate_scores(rows)
    rows = deepcopy(inventory["scores"])
    rows[0]["target"] = "wrong target"
    with pytest.raises(ValueError, match="source identity"):
        addendum.validate_scores(rows)


def test_existing_release_directory_fails_without_preflight(tmp_path, monkeypatch):
    def must_not_run():
        raise AssertionError("Preflight must not run for an existing release")

    monkeypatch.setattr(addendum, "preflight", must_not_run)
    with pytest.raises(FileExistsError, match="refusing overwrite"):
        addendum.release(tmp_path)
