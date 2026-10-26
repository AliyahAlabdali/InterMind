"""Offline v1.1 recovery of follow-up routing and persona discrimination."""

from __future__ import annotations

import csv
import json
import os
from collections import Counter
from pathlib import Path

from evals.datasets.evaluation.followup_cases import CASES
from evals.datasets.evaluation.personas import JOBS, PERSONAS
from evals.harness.metrics import discrimination_metrics, followup_metrics
from evals.recovery_v11.audit import OUTPUT, ROOT, SOURCE, audit, progress, sha
from evals.recovery_v11.latency import HERE, require_lock
from evals.run_interview_eval import _require_frozen_labels

VERSION = "1.1"
METHOD = HERE / "FOLLOWUP_DISCRIMINATION_METHOD_v1.1.md"
MANIFEST = OUTPUT / "RECOVERY_MANIFEST_v1.1.json"
RESULTS = OUTPUT / "followup_discrimination_v1.1"
PRIOR_SHA256 = {
    "evidence_review_frozen/evidence_source_review.lock.json":
        "86561b2cf826796272b19d3d169f70a7131d423950eedce1977c72a4422b49ed",
    "evidence_fidelity_v1.1/RESULT.lock.json":
        "834343ef378f57b054aee5c64bf4a54ff8a0a05c86540a9151f27ef3d382758e",
    "../../../results/20261011T231332Z-v11-preflight/requests.jsonl":
        "07f477e992f9c20b68b3ebda097430195ec2d9d0c814df384853c7fe061bb264",
    "../../../results/20261011T231332Z-v11-preflight/api_ledger.sqlite":
        "edc4d5d9e37dda52df0cc68c7278bb713bd5357ff13b5a7c7a06ac7dd4be6eb2",
    "../../../results/20261011T231332Z-v11-preflight/usage_summary.json":
        "12fbacd6b9592cc16b572c315ad7d07cac886edef9f9945bf5f0d297d4b5045b",
    "../../../results/20261011T231332Z-v11-preflight/run_state.json":
        "9b34076341e8e13d0342098b1727ca29e1bcb170a339b8079a6bdae280589c93",
    "../../../results/20261011T231631Z-v11-latency/requests.jsonl":
        "74353836b12f87375cf194cf0ead131298b341bf4498da52a5c3a39eed9c7cb9",
    "../../../results/20261011T231631Z-v11-latency/api_ledger.sqlite":
        "eb66367c90e24749ceea349159d2a0ca1be77e080d0411ea211dc23aadc6bb6f",
    "../../../results/20261011T231631Z-v11-latency/usage_summary.json":
        "d05037dcc388e10beb4e967b4db74915a6c8886e787a2bf26555b6ee90e86d8a",
    "../../../results/20261011T231631Z-v11-latency/run_state.json":
        "02463c5f4f4a35815a77e87292643640b79a931667f1d9da924e4ea68ec4f10e",
}


def verify_inputs() -> tuple[list[dict], list[dict], dict[str, str], dict]:
    """Require the frozen inventory and all previously locked recovery artifacts."""
    lock = require_lock()
    saved = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if sha(MANIFEST) != (OUTPUT / "RECOVERY_MANIFEST_v1.1.sha256").read_text().strip():
        raise ValueError("Recovery manifest hash changed")
    rebuilt, _ = audit()
    if rebuilt != saved or saved.get("source_status") != "incomplete":
        raise ValueError("Recovery manifest no longer describes the incomplete source")
    roots = {
        "source_files_sha256": SOURCE, "frozen_files_sha256": ROOT,
        "source_code_sha256": ROOT.parent, "recovery_files_sha256": HERE,
    }
    for group, root in roots.items():
        for relative, digest in saved[group].items():
            if sha(root / relative) != digest:
                raise ValueError(f"Recovery source hash changed: {group}/{relative}")
    if (saved["frozen_labels_sha256"]
            != lock["sha256"]["labels/followup_blind.frozen.csv"]
            or saved["study_v1_lock_sha256"]
            != lock["sha256"]["claim_validity/STUDY.lock.json"]
            or saved["pilot_snapshot_sha256"]
            != lock["sha256"]["claim_validity/PILOT_SNAPSHOT_v1.json"]):
        raise ValueError("Recovery manifest and frozen locks disagree")
    for relative, digest in PRIOR_SHA256.items():
        if sha(OUTPUT / relative) != digest:
            raise ValueError(f"Prior v1.1 result changed: {relative}")
    human_review = OUTPUT / "evidence_review_frozen"
    human_lock = json.loads((human_review / "evidence_source_review.lock.json").read_text())
    human_paths = {
        "evidence_source_review_frozen.csv":
            human_review / "evidence_source_review_frozen.csv",
        "evidence_review.py": HERE / "evidence_review.py",
        "PROTOCOL_v1.1.md": HERE / "PROTOCOL_v1.1.md",
        "RECOVERY_MANIFEST_v1.1.json": MANIFEST,
    }
    for name, path in human_paths.items():
        if sha(path) != human_lock["sha256"][name]:
            raise ValueError(f"Prior human-review hash changed: {name}")
    prior_result = OUTPUT / "evidence_fidelity_v1.1"
    prior_lock = json.loads((prior_result / "RESULT.lock.json").read_text())
    prior_paths = {
        "metrics.json": prior_result / "metrics.json",
        "per_report.csv": prior_result / "per_report.csv",
        "PROTOCOL_v1.1.md": HERE / "PROTOCOL_v1.1.md",
        "RECOVERY_MANIFEST_v1.1.json": MANIFEST,
        "evidence_source_review_frozen.csv":
            human_review / "evidence_source_review_frozen.csv",
        "evidence_source_review.lock.json":
            human_review / "evidence_source_review.lock.json",
        "AGGREGATION_METHOD_v1.1.md": HERE / "AGGREGATION_METHOD_v1.1.md",
        "evidence_aggregate.py": HERE / "evidence_aggregate.py",
    }
    for name, path in prior_paths.items():
        if sha(path) != prior_lock["sha256"][name]:
            raise ValueError(f"Prior evidence result changed: {name}")
    labels = _require_frozen_labels()
    rows = progress()
    followups, personas = rows["followup"], rows["persona"]
    cases = {case.case_id: case for case in CASES}
    expected_personas = {persona.persona_id: persona for persona in PERSONAS}
    followup_ids = [row["case_id"] for row in followups]
    persona_ids = [row["persona_id"] for row in personas]
    if (len(followups) != 90 or len(labels) != 90
            or len(set(followup_ids)) != 90 or set(followup_ids) != set(cases)
            or followup_ids != saved["validated_followup_case_ids"]):
        raise ValueError("Recovered follow-up case IDs changed")
    if (len(personas) != 15 or len(set(persona_ids)) != 15
            or set(persona_ids) != set(expected_personas)
            or persona_ids != saved["validated_persona_report_ids"]):
        raise ValueError("Recovered persona report IDs changed")
    if (saved["validation"]["question_assessments"] != 150
            or not any("No per-call token usage" in item
                       for item in saved["missing_provenance"])
            or not any("No saved request payload hashes" in item
                       for item in saved["missing_provenance"])):
        raise ValueError("Recovery provenance disclosure changed")
    return followups, personas, labels, saved


def confusion(rows: list[tuple[str, str]]) -> dict:
    """Small raw-model diagnostic using the same positive class as routed F1."""
    clear = [(label, decision) for label, decision in rows if label != "AMBIGUOUS"]
    tp = sum(label == "FOLLOW_UP_WARRANTED" and decision == "follow_up"
             for label, decision in clear)
    fp = sum(label == "NO_FOLLOW_UP_WARRANTED" and decision == "follow_up"
             for label, decision in clear)
    fn = sum(label == "FOLLOW_UP_WARRANTED" and decision == "advance"
             for label, decision in clear)
    tn = sum(label == "NO_FOLLOW_UP_WARRANTED" and decision == "advance"
             for label, decision in clear)
    if tp + fp + fn + tn != len(clear):
        raise ValueError("Invalid diagnostic labels or decisions")
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
    }


def confusion_category(label: str, decision: str) -> str:
    if label == "AMBIGUOUS":
        return "ambiguous"
    positive = label == "FOLLOW_UP_WARRANTED"
    return ("tp" if positive else "fp") if decision == "follow_up" else (
        "fn" if positive else "tn"
    )


def build_metrics(followups: list[dict], personas: list[dict],
                  labels: dict[str, str], manifest: dict,
                  *, bootstrap_samples: int = 10_000) -> dict:
    cases = {case.case_id: case for case in CASES}
    primary = [(labels[row["case_id"]], row["prediction"]) for row in followups]
    raw = [(labels[row["case_id"]], row["raw_evaluation"]["decision"])
           for row in followups]
    clusters = [f"{cases[row['case_id']].target}\0{cases[row['case_id']].question}"
                for row in followups]
    routed = followup_metrics(primary, cluster_ids=clusters,
                              bootstrap_samples=bootstrap_samples, seed=401)
    routed_check = confusion(primary)
    if any(routed[key] != routed_check[key] for key in routed_check):
        raise ValueError("Frozen follow-up calculation disagrees with diagnostic")
    overrides = []
    for row in followups:
        before, after = row["raw_evaluation"]["decision"], row["prediction"]
        if before == after:
            continue
        label = labels[row["case_id"]]

        overrides.append({
            "case_id": row["case_id"], "human_label": label,
            "raw_model_decision": before, "final_route": after,
            "raw_category": confusion_category(label, before),
            "routed_category": confusion_category(label, after),
        })
    if len(overrides) != 6:
        raise ValueError("Unexpected raw-to-route override count")
    discrimination = discrimination_metrics(personas)
    by_job = {job.jd_id: {} for job in JOBS}
    for row in personas:
        by_job[row["jd_id"]][row["tier"]] = row
    per_job = []
    for job_id, tiers in sorted(by_job.items()):
        if set(tiers) != {"strong", "mixed", "weak"}:
            raise ValueError("Job lacks a frozen persona tier")
        strong, mixed, weak = (tiers[tier] for tier in ("strong", "mixed", "weak"))
        per_job.append({
            "jd_id": job_id,
            "strong_score": strong["score"], "strong_recommendation": strong["recommendation"],
            "mixed_score": mixed["score"], "mixed_recommendation": mixed["recommendation"],
            "weak_score": weak["score"], "weak_recommendation": weak["recommendation"],
            "strong_minus_mixed": round(strong["score"] - mixed["score"], 4),
            "mixed_minus_weak": round(mixed["score"] - weak["score"], 4),
            "strictly_ordered": strong["score"] > mixed["score"] > weak["score"],
        })
    if sum(row["strictly_ordered"] for row in per_job) != discrimination["ordered_jobs"]:
        raise ValueError("Per-job ordering disagrees with frozen metric")
    score_ranges = {tier: {
        "min": min(row["score"] for row in personas if row["tier"] == tier),
        "max": max(row["score"] for row in personas if row["tier"] == tier),
    } for tier in ("strong", "mixed", "weak")}
    return {
        "version": VERSION,
        "source_run_status": "incomplete",
        "metric_status": "separately recovered v1.1; not completed frozen v1.0",
        "follow_up": {
            "primary_prediction": "InterMind final route",
            "human_label_distribution": dict(Counter(labels.values())),
            "raw_model_decision_distribution": dict(Counter(
                row["raw_evaluation"]["decision"] for row in followups)),
            "final_route_distribution": dict(Counter(row["prediction"] for row in followups)),
            "routed_metrics": routed,
            "raw_model_diagnostic": confusion(raw),
            "routing_overrides": overrides,
        },
        "discrimination": {
            **discrimination,
            "score_ranges": score_ranges,
            "per_job": per_job,
            "unexpected_ordering_jobs": [row["jd_id"] for row in per_job
                                        if not row["strictly_ordered"]],
            "pooled_strong_mixed_overlap": (
                score_ranges["strong"]["min"] <= score_ranges["mixed"]["max"]
            ),
            "pooled_mixed_weak_overlap": (
                score_ranges["mixed"]["min"] <= score_ranges["weak"]["max"]
            ),
        },
        "recovery_provenance": {
            "source_run": manifest["source_run"],
            "source_status": manifest["source_status"],
            "missing": manifest["missing_provenance"],
            "followup_case_ids": len(manifest["validated_followup_case_ids"]),
            "persona_report_ids": len(manifest["validated_persona_report_ids"]),
            "question_assessments": manifest["validation"]["question_assessments"],
            "model_provenance": "Returned model IDs and per-request usage are unavailable",
        },
        "limitations": [
            "The source v1.0 run was incomplete; these are separately recovered v1.1 outputs.",
            "Saved report and prediction IDs, source hashes, and report arithmetic validate, "
            "but missing request payloads and returned model IDs cannot be reconstructed.",
            "Follow-up cases share 38 question clusters; the F1 interval resamples clusters.",
            "Persona tiers are authored fixtures over five jobs, not human numeric score labels.",
            "One recovered run cannot estimate stochastic rerun variability or "
            "deployment behavior.",
            "This method was codified after preliminary inspection of recovered outputs.",
        ],
    }


def aggregate() -> Path:
    followups, personas, labels, manifest = verify_inputs()
    metrics = build_metrics(followups, personas, labels, manifest)
    metrics["provenance_sha256"] = {
        "PROTOCOL.md": sha(ROOT / "PROTOCOL.md"),
        "PROTOCOL_v1.1.md": sha(HERE / "PROTOCOL_v1.1.md"),
        "followup_blind.frozen.csv": sha(ROOT / "labels/followup_blind.frozen.csv"),
        "RECOVERY_MANIFEST_v1.1.json": sha(MANIFEST),
        "progress.jsonl": sha(SOURCE / "progress.jsonl"),
        "run_state.json": sha(SOURCE / "run_state.json"),
        "FOLLOWUP_DISCRIMINATION_METHOD_v1.1.md": sha(METHOD),
        "followup_discrimination.py": sha(Path(__file__)),
    }
    RESULTS.mkdir(exist_ok=False)
    metrics_path = RESULTS / "metrics.json"
    with metrics_path.open("x", encoding="utf-8") as file:
        json.dump(metrics, file, indent=2)
        file.write("\n")
    tables = {
        "per_job.csv": metrics["discrimination"]["per_job"],
        "routing_overrides.csv": metrics["follow_up"]["routing_overrides"],
    }
    for name, rows in tables.items():
        with (RESULTS / name).open("x", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    result_lock = RESULTS / "RESULT.lock.json"
    with result_lock.open("x", encoding="utf-8") as file:
        json.dump({"version": VERSION, "source_status": "incomplete", "sha256": {
            **{name: sha(RESULTS / name) for name in
               ("metrics.json", "per_job.csv", "routing_overrides.csv")},
            **metrics["provenance_sha256"],
            **{f"prior:{name}": digest for name, digest in PRIOR_SHA256.items()},
        }}, file, indent=2)
        file.write("\n")
    for path in (metrics_path, RESULTS / "per_job.csv",
                 RESULTS / "routing_overrides.csv", result_lock):
        os.chmod(path, 0o444)
    return RESULTS


if __name__ == "__main__":
    print(aggregate())
