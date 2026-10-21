"""Offline v1.1 aggregation of recovered report evidence quotation fidelity."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from statistics import median

from evals.datasets.evaluation.personas import PERSONAS
from evals.recovery_v11.audit import OUTPUT, audit, progress, sha
from evals.recovery_v11.evidence_review import FROZEN, validate_review
from evals.recovery_v11.latency import HERE, require_lock

VERSION = "1.1"
RESULTS = OUTPUT / "evidence_fidelity_v1.1"
METHOD = HERE / "AGGREGATION_METHOD_v1.1.md"
MANIFEST = OUTPUT / "RECOVERY_MANIFEST_v1.1.json"


def verified_review() -> list[dict[str, str]]:
    """Read only the write-once human copy and verify its provenance lock."""
    require_lock()
    frozen_csv = FROZEN / "evidence_source_review_frozen.csv"
    lock = json.loads((FROZEN / "evidence_source_review.lock.json").read_text())
    expected = {
        "evidence_source_review_frozen.csv": frozen_csv,
        "evidence_review.py": HERE / "evidence_review.py",
        "PROTOCOL_v1.1.md": HERE / "PROTOCOL_v1.1.md",
        "RECOVERY_MANIFEST_v1.1.json": MANIFEST,
    }
    if (lock.get("version") != "1.1-recovered-evidence-review"
            or lock.get("source_run_status") != "incomplete"
            or lock.get("human_reviewer_count") != 1
            or lock.get("reviewed_rows") != 22
            or set(lock.get("sha256", {})) != set(expected)):
        raise ValueError("Frozen human-review lock is incomplete")
    for name, path in expected.items():
        if sha(path) != lock["sha256"][name]:
            raise ValueError(f"Frozen human-review hash changed: {name}")
    rows = validate_review(frozen_csv)
    if len(rows) != 22 or dict(Counter(row["verdict"] for row in rows)) != lock["verdict_counts"]:
        raise ValueError("Frozen human-review counts changed")
    return rows


def evidence_inventory() -> tuple[list[dict], list[str]]:
    """Rebuild saved report locations; use the frozen audit for auto/review routing."""
    manifest, unresolved = audit()
    if manifest != json.loads(MANIFEST.read_text(encoding="utf-8")):
        raise ValueError("Recovery manifest disagrees with source inventory")
    unresolved_ids = {row["evidence_id"] for row in unresolved}
    if len(unresolved) != 22 or len(unresolved_ids) != 22:
        raise ValueError("Unresolved evidence IDs changed")
    candidates = {candidate.persona_id: candidate for candidate in PERSONAS}
    reports = progress()["persona"]
    records = []
    for report in reports:
        report_id = report["persona_id"]
        candidate = candidates[report_id]
        answer_index = {answer.target: i for i, answer in enumerate(candidate.answers, 1)}
        for question in report["report"]["question_evaluations"]:
            target_index = answer_index[question["target"]]
            for item in question["evidence"]:
                evidence_id = "ev-" + hashlib.sha256(
                    f"{report_id}\0{question['target_id']}\0{item}".encode()
                ).hexdigest()[:20]
                records.append({
                    "evidence_id": evidence_id,
                    "report_id": report_id,
                    "target_id": question["target_id"],
                    "target_answer_index": target_index,
                    "needs_review": evidence_id in unresolved_ids,
                })
    ids = [record["evidence_id"] for record in records]
    if (len(records) != 239 or len(set(ids)) != 239
            or sum(record["needs_review"] for record in records) != 22
            or {record["evidence_id"] for record in records if record["needs_review"]}
            != unresolved_ids or len(reports) != 15):
        raise ValueError("Recovered evidence inventory is incomplete or duplicated")
    return records, [report["persona_id"] for report in reports]


def calculate(records: list[dict], reviews: list[dict], report_ids: list[str]) -> dict:
    """Count strings and report clusters without an independence assumption."""
    if len({record["evidence_id"] for record in records}) != len(records):
        raise ValueError("Duplicate evidence ID")
    by_id = {row["evidence_id"]: row for row in reviews}
    if (len(by_id) != len(reviews)
            or set(by_id) != {record["evidence_id"] for record in records
                              if record["needs_review"]}):
        raise ValueError("Human review IDs do not match unresolved evidence")
    if len(set(report_ids)) != len(report_ids):
        raise ValueError("Duplicate report ID")
    per_report = {report_id: {
        "report_id": report_id, "evidence_strings": 0, "automatically_attributed": 0,
        "human_supported": 0, "unsupported": 0, "cannot_tell": 0,
        "cross_target_human_support": 0,
    } for report_id in report_ids}
    targets = {report_id: set() for report_id in report_ids}
    for record in records:
        report_id = record["report_id"]
        if report_id not in per_report:
            raise ValueError("Unknown report ID")
        row = per_report[report_id]
        row["evidence_strings"] += 1
        targets[report_id].add(record["target_id"])
        if not record["needs_review"]:
            row["automatically_attributed"] += 1
            continue
        review = by_id[record["evidence_id"]]
        verdict = review["verdict"]
        if verdict == "supported":
            row["human_supported"] += 1
            source_indices = {int(part.strip()) for part in
                              review["source_answer_index"].split(";")}
            if record["target_answer_index"] not in source_indices:
                row["cross_target_human_support"] += 1
        elif verdict in {"unsupported", "cannot_tell"}:
            row[verdict] += 1
        else:
            raise ValueError("Invalid human verdict")
    reports = []
    for report_id, row in sorted(per_report.items()):
        row["supported"] = row["automatically_attributed"] + row["human_supported"]
        if row["supported"] + row["unsupported"] + row["cannot_tell"] != row["evidence_strings"]:
            raise ValueError("Report totals do not reconcile")
        row["distinct_report_target_answers"] = len(targets[report_id])
        row["quotation_fidelity_rate"] = (
            row["supported"] / row["evidence_strings"] if row["evidence_strings"] else None
        )
        reports.append(row)
    summed = {key: sum(row[key] for row in reports) for key in (
        "evidence_strings", "automatically_attributed", "human_supported",
        "supported", "unsupported", "cannot_tell", "cross_target_human_support",
    )}
    if summed["evidence_strings"] != len(records):
        raise ValueError("Overall totals do not reconcile")
    rates = [row["quotation_fidelity_rate"] for row in reports
             if row["quotation_fidelity_rate"] is not None]
    sizes = [row["evidence_strings"] for row in reports]
    return {
        "version": VERSION,
        "metric_name": "v1.1 recovered report evidence quotation fidelity",
        "source_run_status": "incomplete",
        "counts": summed,
        "quotation_fidelity_rate": summed["supported"] / summed["evidence_strings"],
        "report_cluster_summary": {
            "reports": len(reports), "report_evidence_min": min(sizes),
            "report_evidence_median": median(sizes), "report_evidence_max": max(sizes),
            "report_rate_min": min(rates), "report_rate_median": median(rates),
            "report_rate_max": max(rates),
        },
        "per_report": reports,
        "limitations": [
            "Incomplete v1.0 source run; recovered report outputs lack per-turn histories.",
            "Automatically attributed exact strings were not each independently human reviewed.",
            "One human reviewer adjudicated unresolved strings; no independent "
            "human agreement estimate.",
            "Evidence strings within a report or answer are dependent; no string-level CI.",
            "Quotation/source fidelity does not establish claim or score validity.",
        ],
    }


def aggregate() -> Path:
    """Write the separately versioned result once after all provenance checks."""
    reviews = verified_review()
    records, report_ids = evidence_inventory()
    metrics = calculate(records, reviews, report_ids)
    if (metrics["counts"]["evidence_strings"] != 239
            or metrics["counts"]["automatically_attributed"] != 217
            or sum(review["verdict"] == "supported" for review in reviews)
            != metrics["counts"]["human_supported"]):
        raise ValueError("Protocol evidence denominators changed")
    metrics["provenance_sha256"] = {
        "PROTOCOL_v1.1.md": sha(HERE / "PROTOCOL_v1.1.md"),
        "RECOVERY_MANIFEST_v1.1.json": sha(MANIFEST),
        "evidence_source_review_frozen.csv": sha(FROZEN / "evidence_source_review_frozen.csv"),
        "evidence_source_review.lock.json": sha(FROZEN / "evidence_source_review.lock.json"),
        "AGGREGATION_METHOD_v1.1.md": sha(METHOD),
        "evidence_aggregate.py": sha(Path(__file__)),
    }
    RESULTS.mkdir(exist_ok=False)
    metrics_path = RESULTS / "metrics.json"
    with metrics_path.open("x", encoding="utf-8") as file:
        json.dump(metrics, file, indent=2)
        file.write("\n")
    report_path = RESULTS / "per_report.csv"
    with report_path.open("x", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(metrics["per_report"][0]))
        writer.writeheader()
        writer.writerows(metrics["per_report"])
    lock_path = RESULTS / "RESULT.lock.json"
    with lock_path.open("x", encoding="utf-8") as file:
        json.dump({"version": VERSION, "sha256": {
            "metrics.json": sha(metrics_path), "per_report.csv": sha(report_path),
            **metrics["provenance_sha256"],
        }}, file, indent=2)
        file.write("\n")
    for path in (metrics_path, report_path, lock_path):
        os.chmod(path, 0o444)
    return RESULTS


if __name__ == "__main__":
    print(aggregate())
