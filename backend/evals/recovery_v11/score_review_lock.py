"""Validate and freeze the completed v1.1a score-band review, offline only.

From backend/: python -m evals.recovery_v11.score_review_lock freeze
No score-validity metric or comparison is calculated here.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from evals.recovery_v11 import claim_score_addendum as addendum
from evals.recovery_v11.audit import sha

REVIEW = addendum.HERE / "human_review" / "intermind_final_score_review_45.csv"
RELEASED = addendum.OUT / addendum.SHEET
MANIFEST = addendum.OUT / "PROVENANCE_MANIFEST.json"
RELEASE_LOCK = addendum.OUT / "RELEASE.lock.json"
COMPLETED_LOCK = addendum.OUT / "COMPLETED_SCORE_REVIEW.lock.json"
EXPECTED_SHA256 = {
    MANIFEST: "3f5d1795f03fd71cc8e00de4f4b17ed2664fdd8cdd2aa6c81cd73e50c1da3bc5",
    RELEASE_LOCK: "03600b880d18b9ff06ca51fec3a1884a28fcf722041621cda0f46229c55989e8",
    RELEASED: "2fa9eca019b2e1a0d73ff103022add1346d6db572a109325e8aa09216ee47e0b",
}
VERDICTS = ("DEFENSIBLE", "NOT_DEFENSIBLE", "UNCLEAR")
OMISSIONS = ("YES", "NO", "UNCLEAR")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames != list(addendum.SCORE_FIELDS):
            raise ValueError(f"Score CSV columns changed: {path.name}")
        rows = list(reader)
    if any(set(row) != set(addendum.SCORE_FIELDS) or None in row.values() for row in rows):
        raise ValueError(f"Malformed score CSV row: {path.name}")
    return rows


def validate_rows(original: list[dict], reviewed: list[dict]) -> tuple[dict, dict]:
    """Compare every source field exactly and validate only allowed human edits."""
    if len(original) != 45 or len(reviewed) != 45:
        raise ValueError(f"Expected 45 assessment rows; found {len(reviewed)}")
    expected = [row["score_review_id"] for row in original]
    actual = [row["score_review_id"] for row in reviewed]
    if len(set(expected)) != 45:
        raise ValueError("Released assessment IDs are not unique")
    if len(set(actual)) != 45:
        raise ValueError("Duplicate score_review_id in completed review")
    if set(actual) != set(expected):
        raise ValueError("Missing or unknown score_review_id in completed review")
    if actual != expected:
        raise ValueError("Completed review row order changed")
    source_fields = [field for field in addendum.SCORE_FIELDS
                     if field not in addendum.JUDGMENT_FIELDS]
    for index, (source, row) in enumerate(zip(original, reviewed, strict=True), start=1):
        for field in source_fields:
            if row[field] != source[field]:
                raise ValueError(f"Row {index} {row['score_review_id']}: source field "
                                 f"{field} changed")
        if row["verdict"] not in VERDICTS:
            raise ValueError(f"Row {index} {row['score_review_id']}: invalid verdict")
        if row["material_omission"] not in OMISSIONS:
            raise ValueError(f"Row {index} {row['score_review_id']}: invalid material_omission")
        if row["verdict"] != "DEFENSIBLE" and not row["note"].strip():
            raise ValueError(f"Row {index} {row['score_review_id']}: missing explanatory note")
        if row["material_omission"] != "NO" and not row["omission_detail"].strip():
            raise ValueError(f"Row {index} {row['score_review_id']}: missing omission_detail")
    verdicts = Counter(row["verdict"] for row in reviewed)
    omissions = Counter(row["material_omission"] for row in reviewed)
    return ({name: verdicts[name] for name in VERDICTS},
            {name: omissions[name] for name in OMISSIONS})


def validate(review_path: Path = REVIEW) -> tuple[dict, dict]:
    """Verify frozen provenance and review contents without writing anything."""
    if review_path.name != REVIEW.name:
        raise ValueError("Completed review filename changed")
    for path, expected in EXPECTED_SHA256.items():
        if sha(path) != expected:
            raise ValueError(f"Frozen v1.1a release hash changed: {path.name}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    release_lock = json.loads(RELEASE_LOCK.read_text(encoding="utf-8"))
    if (manifest.get("version") != "1.1a" or release_lock.get("version") != "1.1a"
            or manifest.get("score_sheet_path") != addendum._relative(RELEASED)
            or manifest.get("score_sheet_sha256_at_release") != sha(RELEASED)
            or manifest.get("score_sheet_fields") != list(addendum.SCORE_FIELDS)
            or manifest.get("validation", {}).get("score_rows") != 45
            or manifest.get("validation", {}).get("human_score_verdicts_entered") != 0
            or manifest.get("score_review_lock_created") is not False):
        raise ValueError("v1.1a release manifest changed or is incomplete")
    for relative, digest in manifest["input_sha256"].items():
        if sha(addendum.REPO / relative) != digest:
            raise ValueError(f"Frozen manifest source hash changed: {relative}")
    for relative, digest in release_lock["sha256"].items():
        if sha(addendum.REPO / relative) != digest:
            raise ValueError(f"Frozen release-lock source hash changed: {relative}")
    addendum.preflight()  # Also rechecks all v1.0/v1.1 source and sample locks.
    return validate_rows(_read_csv(RELEASED), _read_csv(review_path))


def freeze(review_path: Path = REVIEW, lock_path: Path = COMPLETED_LOCK,
           *, protect: bool = True) -> dict:
    """Create one completed-review lock with exclusive, write-once output."""
    if lock_path.exists():
        raise FileExistsError("Completed score-review lock already exists")
    review_digest = sha(review_path)
    verdicts, omissions = validate(review_path)
    if sha(review_path) != review_digest:
        raise ValueError("Completed review changed during validation")
    if lock_path.exists():
        raise FileExistsError("Completed score-review lock already exists")
    payload = {
        "version": "1.1a",
        "status": "completed_human_review_frozen_metrics_not_calculated",
        "locked_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "completed_review_path": addendum._relative(review_path),
        "completed_review_sha256": review_digest,
        "release_lock_path": addendum._relative(RELEASE_LOCK),
        "release_lock_sha256": sha(RELEASE_LOCK),
        "released_sheet_path": addendum._relative(RELEASED),
        "released_sheet_sha256": sha(RELEASED),
        "release_manifest_path": addendum._relative(MANIFEST),
        "release_manifest_sha256": sha(MANIFEST),
        "addendum_path": addendum._relative(addendum.ADDENDUM),
        "addendum_sha256": sha(addendum.ADDENDUM),
        "validated_assessments": 45,
        "verdict_counts": verdicts,
        "material_omission_counts": omissions,
        "internal_methodological_provenance": {
            "basis": "operator-reported at completed-review lock",
            "final_judgments": "one human reviewer adopted final score-band judgments after "
                               "majority comparison of three AI-generated assessments",
            "AI_assessments_are_not_independent_human_raters": True,
            "independent_initial_blind_human_score_review_documented": False,
            "independent_initial_blind_human_claim_review_documented": False,
            "original_claim_lock_exists": False,
            "retrospective_v1_1a_deviation": True,
            "source_run_status": "incomplete",
            "human_inter_rater_reliability_claimed": False,
            "reviewer_timestamps_inferred": False,
        },
        "score_validity_metrics_calculated": False,
        "score_comparison_report_generated": False,
    }
    with lock_path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    if protect:
        os.chmod(lock_path, 0o444)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "freeze"))
    args = parser.parse_args()
    if args.command == "validate":
        verdicts, omissions = validate()
        result = {"validated_assessments": 45, "verdict_counts": verdicts,
                  "material_omission_counts": omissions}
    else:
        result = freeze()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
