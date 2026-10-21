"""Offline regression checks for retrospective v1.1a result aggregation."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import pytest

from evals.recovery_v11 import claim_score_results as results

pytestmark = pytest.mark.private_history


class ClaimScoreResultsTests(TestCase):
    def test_locked_inputs_and_expected_counts(self) -> None:
        claims, scores, inventory = results.verify_inputs()
        data = results.analyze(claims, scores, inventory)
        self.assertEqual(
            data["claims"]["counts"],
            {
                "SUPPORTED": 221,
                "PARTIALLY_SUPPORTED": 18,
                "UNSUPPORTED": 6,
                "UNCLEAR": 0,
            },
        )
        self.assertEqual(
            data["scores"]["counts"],
            {
                "DEFENSIBLE": 44,
                "NOT_DEFENSIBLE": 1,
                "UNCLEAR": 0,
            },
        )
        self.assertEqual(
            data["material_omissions"]["counts"],
            {
                "YES": 6,
                "NO": 39,
                "UNCLEAR": 0,
            },
        )
        self.assertEqual(len(data["per_report"]), 15)
        self.assertEqual(len(data["per_target"]), 15)
        self.assertEqual(data["overall_score_and_recommendation_arithmetic_checked_reports"], 15)

    def test_lock_hash_mismatch_blocks_analysis(self) -> None:
        with patch.object(results, "LOCK_SHA256", "0" * 64):
            with self.assertRaisesRegex(ValueError, "lock hash changed"):
                results.verify_inputs()

    def test_duplicate_score_id_is_rejected(self) -> None:
        actual = results.read_csv

        def changed(path: Path):
            fields, rows = actual(path)
            if path.name == "intermind_final_score_review_45.csv":
                rows = copy.deepcopy(rows)
                rows[1]["score_review_id"] = rows[0]["score_review_id"]
            return fields, rows

        with patch.object(results, "read_csv", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "Score assessment IDs or order changed"):
                results.verify_inputs()

    def test_changed_source_field_and_invalid_judgment_are_rejected(self) -> None:
        actual = results.read_csv
        for field, value, message in (
            ("score", "0.99", "Score source field changed"),
            ("verdict", "MAYBE", "Invalid score review judgment"),
            ("material_omission", "MAYBE", "Invalid score review judgment"),
        ):
            with self.subTest(field=field):

                def changed(path: Path, field: str = field, value: str = value):
                    fields, rows = actual(path)
                    if path.name == "intermind_final_score_review_45.csv":
                        rows = copy.deepcopy(rows)
                        rows[0][field] = value
                    return fields, rows

                with patch.object(results, "read_csv", side_effect=changed):
                    with self.assertRaisesRegex(ValueError, message):
                        results.verify_inputs()

    def test_cluster_interval_is_deterministic(self) -> None:
        claims, scores, inventory = results.verify_inputs()
        reports = results.analyze(claims, scores, inventory)["per_report"]
        first = results.cluster_sensitivity(reports, draws=101, seed=12)
        self.assertEqual(first, results.cluster_sensitivity(reports, draws=101, seed=12))
        for low, high in first["intervals"].values():
            self.assertLessEqual(low, high)
            self.assertGreaterEqual(low, 0)
            self.assertLessEqual(high, 100)

    def test_write_once_results_and_output_hashes(self) -> None:
        with TemporaryDirectory() as temp:
            target = Path(temp) / "results"
            data = results.run(target)
            lock = json.loads((target / "RESULTS.lock.json").read_text(encoding="utf-8"))
            self.assertEqual(data["claims"]["n"], 245)
            for name, digest in lock["outputs_sha256"].items():
                self.assertEqual(results.sha(target / name), digest)
            with self.assertRaises(FileExistsError):
                results.run(target)
