"""Check the private, byte-locked evaluation bundle before historical tests run.

Run from backend/: ``python -m evals.private_history``. No model or network call is made.
The public checkout test command is documented separately; plain pytest still runs all tests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from evals.recovery_v11 import claim_score_addendum, claim_score_results, score_review_lock
from evals.recovery_v11.followup_discrimination import PRIOR_SHA256
from evals.recovery_v11.provenance_v12 import EVAL_ROOT, LOCK, verify_historical_provenance

RESULTS_ROOT = EVAL_ROOT / "results"
PILOT_SNAPSHOT = EVAL_ROOT / "claim_validity" / "PILOT_SNAPSHOT_v1.json"
RECOVERY_RESULT_LOCK = (
    EVAL_ROOT
    / "recovery_v11/artifacts/20261011T223751Z/followup_discrimination_v1.1/RESULT.lock.json"
)
PILOT = "20261011T214346Z-pilot"
FINAL = "20261011T223751Z-final"
PREFLIGHT = "20261011T231332Z-v11-preflight"
LATENCY = "20261011T231631Z-v11-latency"
EXPECTED_COUNTS = {PILOT: 9, FINAL: 2, PREFLIGHT: 4, LATENCY: 4}
HISTORICAL_TESTS = (
    "tests/unit/test_claim_score_addendum.py",
    "tests/unit/test_claim_score_results.py",
    "tests/unit/test_claim_validity_study.py",
    "tests/unit/test_interview_eval_harness.py",
    "tests/unit/test_recovered_claim_study.py",
    "tests/unit/test_recovered_evidence_aggregate.py",
    "tests/unit/test_recovered_evidence_review.py",
    "tests/unit/test_recovered_followup_discrimination.py",
    "tests/unit/test_recovery_provenance_v12.py",
    "tests/unit/test_recovery_v11.py",
    "tests/unit/test_score_review_lock.py",
)
FROZEN_REVIEW = (
    EVAL_ROOT
    / "recovery_v11/artifacts/20261011T223751Z/evidence_review_frozen"
    / "evidence_source_review.lock.json"
)


class PrivateArtifactError(ValueError):
    """A private historical artifact or its published lock is unavailable or changed."""


def _json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PrivateArtifactError(f"Historical lock unavailable or invalid: {path}") from exc


def required_artifacts() -> dict[Path, str]:
    """Read the original hashes for the 19 ignored results; never calculate replacements."""
    pilot = _json(PILOT_SNAPSHOT)
    if pilot.get("pilot_directory") != f"results/{PILOT}":
        raise PrivateArtifactError("Frozen pilot directory changed")
    expected = {Path(PILOT) / name: digest for name, digest in pilot["file_sha256"].items()}

    lock = _json(LOCK)
    final_entries = {
        relative: digest
        for relative, digest in lock["sha256"].items()
        if relative.startswith("results/")
    }
    if set(final_entries) != {
        f"results/{FINAL}/progress.jsonl",
        f"results/{FINAL}/run_state.json",
    }:
        raise PrivateArtifactError("Frozen recovery result file list changed")
    expected.update({Path(relative.removeprefix("results/")): digest
                     for relative, digest in final_entries.items()})

    result_lock = _json(RECOVERY_RESULT_LOCK)
    result_hashes = result_lock.get("sha256", {})
    for relative, digest in PRIOR_SHA256.items():
        if result_hashes.get(f"prior:{relative}") != digest:
            raise PrivateArtifactError(f"Prior result lock changed: {relative}")
        if "results/" not in relative:
            continue  # The two earlier result locks are public frozen inputs.
        if relative.count("results/") != 1:
            raise PrivateArtifactError(f"Invalid prior result path: {relative}")
        tail = relative.split("results/", 1)[1]
        if Path(tail).parts[0] not in {PREFLIGHT, LATENCY}:
            raise PrivateArtifactError(f"Unexpected prior result path: {relative}")
        expected[Path(tail)] = digest

    actual_counts = {directory: sum(path.parts[0] == directory for path in expected)
                     for directory in EXPECTED_COUNTS}
    if actual_counts != EXPECTED_COUNTS or len(expected) != 19:
        raise PrivateArtifactError("Private artifact list is incomplete or changed")
    if any(re.fullmatch(r"[0-9a-f]{64}", digest) is None for digest in expected.values()):
        raise PrivateArtifactError("Private artifact lock contains an invalid SHA-256 digest")
    return dict(sorted(expected.items(), key=lambda item: item[0].as_posix()))


def required_private_inputs() -> dict[Path, str]:
    """Read existing frozen locks for eight other answer-bearing review inputs."""
    try:
        lock = _json(LOCK)["sha256"]
        completed_path = score_review_lock.COMPLETED_LOCK
        if (
            hashlib.sha256(completed_path.read_bytes()).hexdigest()
            != claim_score_results.LOCK_SHA256
        ):
            raise PrivateArtifactError("Frozen completed-review lock changed")
        completed = _json(completed_path)
        if hashlib.sha256(FROZEN_REVIEW.read_bytes()).hexdigest() != PRIOR_SHA256[
            "evidence_review_frozen/evidence_source_review.lock.json"
        ]:
            raise PrivateArtifactError("Frozen evidence-review lock changed")
        evidence = _json(FROZEN_REVIEW)
        base = Path("recovery_v11/artifacts/20261011T223751Z")
        expected = {
            Path("labels/followup_blind.csv"): lock["labels/followup_blind.csv"],
            Path("labels/followup_blind.frozen.csv"):
                lock["labels/followup_blind.frozen.csv"],
            Path("recovery_v11/human_review/intermind_final_user_adjudicated_245.csv"):
                claim_score_addendum.BASELINE_SHA256[
                    "intermind_final_user_adjudicated_245.csv"
                ],
            Path("recovery_v11/human_review/intermind_final_score_review_45.csv"):
                completed["completed_review_sha256"],
            base / "claim_score_addendum_v1.1a/scores_band_review_v1.1a.csv":
                score_review_lock.EXPECTED_SHA256[score_review_lock.RELEASED],
            base / "claim_validity_v1.1/claims_initial_blind.csv":
                claim_score_addendum.BASELINE_SHA256["claims_initial_blind.csv"],
            base / "claim_validity_v1.1/inventory.json":
                claim_score_addendum.BASELINE_SHA256["inventory.json"],
            base / "evidence_review_frozen/evidence_source_review_frozen.csv":
                evidence["sha256"]["evidence_source_review_frozen.csv"],
        }
    except (OSError, KeyError) as exc:
        raise PrivateArtifactError("Frozen private-review lock unavailable or incomplete") from exc
    if len(expected) != 8 or any(
        re.fullmatch(r"[0-9a-f]{64}", digest) is None for digest in expected.values()
    ):
        raise PrivateArtifactError("Frozen private-review hash list changed")
    return expected


def _verify_file(root: Path, relative: Path, digest: str) -> None:
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise PrivateArtifactError(f"Unsafe private artifact path: {relative}")
    try:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise PrivateArtifactError(f"Missing private historical artifact: {relative}") from exc
    if actual != digest:
        raise PrivateArtifactError(f"Altered private historical artifact: {relative}")


def verify_bundle(bundle_root: Path, expected: dict[Path, str] | None = None) -> int:
    """Hash every required file's raw bytes, including original CRLF where present."""
    expected = expected if expected is not None else required_artifacts()
    for relative, digest in expected.items():
        _verify_file(bundle_root, relative, digest)

    directories = {relative.parts[0] for relative in expected}
    for directory in sorted(directories):
        expected_names = {path.name for path in expected if path.parts[0] == directory}
        actual_names = {path.name for path in (bundle_root / directory).iterdir()}
        if actual_names != expected_names:
            raise PrivateArtifactError(f"Private historical artifact file set changed: {directory}")
    return len(expected)


def verify_private_inputs(eval_root: Path, expected: dict[Path, str] | None = None) -> int:
    """Verify separately ignored frozen reviews against their existing lock hashes."""
    expected = expected if expected is not None else required_private_inputs()
    for relative, digest in expected.items():
        _verify_file(eval_root, relative, digest)
    return len(expected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Verify bytes without pytest")
    parser.add_argument(
        "--bundle-root", type=Path, default=EVAL_ROOT,
        help="Restored evals/ tree; accepted only with --check-only",
    )
    args = parser.parse_args()
    if not args.check_only and args.bundle_root.resolve() != EVAL_ROOT.resolve():
        parser.error("--bundle-root requires --check-only; tests read the local ignored files")
    try:
        result_count = verify_bundle(args.bundle_root / "results")
        review_count = verify_private_inputs(args.bundle_root)
        if args.bundle_root.resolve() == EVAL_ROOT.resolve():
            verify_historical_provenance()
    except (PrivateArtifactError, ValueError) as exc:
        parser.exit(1, f"Private historical verification failed: {exc}\n")
    print(
        f"Verified {result_count} original private results and {review_count} frozen "
        "review inputs against historical SHA-256 locks."
    )
    if args.check_only:
        return 0
    import pytest

    return pytest.main(["-q", *HISTORICAL_TESTS])


if __name__ == "__main__":
    raise SystemExit(main())
