"""Validate and freeze the one-human recovered evidence source review offline."""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from pathlib import Path

from evals.recovery_v11.audit import OUTPUT, audit, sha
from evals.recovery_v11.latency import HERE, require_lock

REVIEW = OUTPUT / "evidence_source_review_blind.csv"
FROZEN = OUTPUT / "evidence_review_frozen"
HUMAN_COLUMNS = ("source_answer_index", "verdict", "note")
VERDICTS = {"supported", "unsupported", "cannot_tell"}


def validate_review(path: Path | None = None) -> list[dict[str, str]]:
    """Check IDs, unchanged blind context, and every independent human judgment."""
    require_lock()
    path = path or REVIEW
    _, expected = audit()
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != list(expected[0]):
            raise ValueError("Blind review columns changed")
        rows = list(reader)
    if len(rows) != len(expected) or len({row["evidence_id"] for row in rows}) != len(expected):
        raise ValueError("Missing or duplicate evidence IDs")
    for actual, original in zip(rows, expected, strict=True):
        if any(actual.get(key) != value for key, value in original.items()
               if key not in HUMAN_COLUMNS):
            raise ValueError("Evidence ID, order, or blind source context changed")
        verdict = actual["verdict"]
        if verdict not in VERDICTS:
            raise ValueError(f"Missing or invalid verdict for {actual['evidence_id']}")
        sources = actual["source_answer_index"].strip()
        indices = [part.strip() for part in sources.split(";")] if sources else []
        if any(not part.isdigit() or not 1 <= int(part) <= 10 for part in indices):
            raise ValueError(f"Invalid source answer index for {actual['evidence_id']}")
        if len(indices) != len(set(indices)):
            raise ValueError(f"Duplicate source answer index for {actual['evidence_id']}")
        if verdict == "supported" and not indices:
            raise ValueError(f"Supported evidence needs a source answer: {actual['evidence_id']}")
        if (verdict != "supported" or len(indices) > 1) and not actual["note"].strip():
            raise ValueError(f"Explanation required for {actual['evidence_id']}")
    return rows


def freeze_review() -> Path:
    """Create a write-once copy and lock; never change the human's working CSV."""
    rows = validate_review()
    FROZEN.mkdir(exist_ok=False)
    target = FROZEN / "evidence_source_review_frozen.csv"
    with target.open("xb") as file:
        file.write(REVIEW.read_bytes())
        file.flush()
        os.fsync(file.fileno())
    lock = {
        "version": "1.1-recovered-evidence-review",
        "source_run_status": "incomplete",
        "human_reviewer_count": 1,
        "reviewed_rows": len(rows),
        "verdict_counts": dict(Counter(row["verdict"] for row in rows)),
        "sha256": {
            "evidence_source_review_frozen.csv": sha(target),
            "evidence_review.py": sha(Path(__file__)),
            "PROTOCOL_v1.1.md": sha(HERE / "PROTOCOL_v1.1.md"),
            "RECOVERY_MANIFEST_v1.1.json": sha(OUTPUT / "RECOVERY_MANIFEST_v1.1.json"),
        },
    }
    lock_path = FROZEN / "evidence_source_review.lock.json"
    with lock_path.open("x", encoding="utf-8") as file:
        json.dump(lock, file, indent=2)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    os.chmod(target, 0o444)
    os.chmod(lock_path, 0o444)
    return FROZEN


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "freeze"])
    args = parser.parse_args()
    if args.command == "validate":
        print(f"Validated {len(validate_review())} completed human reviews")
    else:
        print(freeze_review())


if __name__ == "__main__":
    main()
