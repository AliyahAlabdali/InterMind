"""Offline checks for the separately versioned recovered quotation-fidelity result."""

import pytest

from evals.recovery_v11.evidence_aggregate import (
    calculate,
    evidence_inventory,
    verified_review,
)

pytestmark = pytest.mark.private_history


def test_aggregation_counts_and_report_clustering():
    records = [
        {"evidence_id": "a", "report_id": "r1", "target_id": "t1",
         "target_answer_index": 1, "needs_review": False},
        {"evidence_id": "b", "report_id": "r1", "target_id": "t1",
         "target_answer_index": 1, "needs_review": True},
        {"evidence_id": "c", "report_id": "r2", "target_id": "t2",
         "target_answer_index": 2, "needs_review": True},
        {"evidence_id": "d", "report_id": "r2", "target_id": "t3",
         "target_answer_index": 3, "needs_review": True},
    ]
    reviews = [
        {"evidence_id": "b", "verdict": "supported", "source_answer_index": "2"},
        {"evidence_id": "c", "verdict": "unsupported", "source_answer_index": ""},
        {"evidence_id": "d", "verdict": "cannot_tell", "source_answer_index": ""},
    ]
    result = calculate(records, reviews, ["r1", "r2"])
    assert result["counts"] == {
        "evidence_strings": 4, "automatically_attributed": 1,
        "human_supported": 1, "supported": 2,
        "unsupported": 1, "cannot_tell": 1,
        "cross_target_human_support": 1,
    }
    assert result["quotation_fidelity_rate"] == 0.5
    assert result["report_cluster_summary"]["reports"] == 2
    assert result["per_report"][0]["distinct_report_target_answers"] == 1
    assert result["per_report"][1]["distinct_report_target_answers"] == 2


def test_aggregation_rejects_missing_review_or_duplicate_evidence():
    record = {"evidence_id": "a", "report_id": "r", "target_id": "t",
              "target_answer_index": 1, "needs_review": True}
    with pytest.raises(ValueError, match="Human review IDs"):
        calculate([record], [], ["r"])
    with pytest.raises(ValueError, match="Duplicate evidence ID"):
        calculate([record, record], [], ["r"])


def test_frozen_recovery_inventory_and_review_reconcile():
    records, reports = evidence_inventory()
    reviews = verified_review()
    assert len(records) == 239
    assert len(reports) == len(set(reports)) == 15
    assert sum(record["needs_review"] for record in records) == len(reviews) == 22
    result = calculate(records, reviews, reports)
    assert result["counts"]["automatically_attributed"] == 217
    assert result["counts"]["evidence_strings"] == 239
