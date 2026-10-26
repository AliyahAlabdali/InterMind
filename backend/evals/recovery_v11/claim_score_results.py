"""Offline, write-once analysis of the retrospective v1.1a reviews.

Run from backend/: python -m evals.recovery_v11.claim_score_results
This module uses only the standard library and never invokes a model.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = HERE / "artifacts" / "20261011T223751Z"
RELEASE = BASE / "claim_score_addendum_v1.1a"
STUDY = BASE / "claim_validity_v1.1"
RESULTS = RELEASE / "results_v1.1a"
LOCK = RELEASE / "COMPLETED_SCORE_REVIEW.lock.json"
LOCK_SHA256 = "398f394ad84f8eae556222ec2976d636d3690c2e1102de38555517b98da0d0ad"
CLAIM_VERDICTS = ("SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "UNCLEAR")
SCORE_VERDICTS = ("DEFENSIBLE", "NOT_DEFENSIBLE", "UNCLEAR")
OMISSIONS = ("YES", "NO", "UNCLEAR")
JUDGMENT_FIELDS = {"verdict", "note", "material_omission", "omission_detail"}
WEIGHTS = {"competency": 0.4, "technology": 0.4, "task": 0.2}
THRESHOLDS = ((0.85, "strong_hire"), (0.65, "hire"), (0.45, "consider"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, strict=True)
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)):
            raise ValueError(f"Duplicate CSV column: {path}")
        rows = list(reader)
    if any(set(row) != set(fields) or None in row.values() for row in rows):
        raise ValueError(f"Malformed CSV row: {path}")
    return fields, rows


def _locked_path(lock: dict, prefix: str) -> Path:
    path = REPO / lock[f"{prefix}_path"]
    if sha(path) != lock[f"{prefix}_sha256"]:
        raise ValueError(f"Frozen {prefix} hash changed")
    return path


def _verify_upstream_locks() -> None:
    """Check nested v1.0 study, label, dataset, and original pilot locks."""
    evals = REPO / "backend/evals"
    study = evals / "claim_validity"
    study_lock = read_json(study / "STUDY.lock.json")
    paths = {
        "PROTOCOL_v1.md": study / "PROTOCOL_v1.md",
        "RUBRIC_v1.md": study / "RUBRIC_v1.md",
        "SAMPLE_v1.json": study / "SAMPLE_v1.json",
        "study.py": study / "study.py",
        "v1_protocol": evals / "PROTOCOL.md",
        "v1_protocol_lock": evals / "PROTOCOL.lock.json",
        "v1_labels": evals / "labels/followup_blind.csv",
        "v1_labels_frozen": evals / "labels/followup_blind.frozen.csv",
        "v1_labels_lock": evals / "labels/followup_labels.lock.json",
        "personas": evals / "datasets/evaluation/personas.py",
        "personas_sample": evals / "datasets/evaluation/personas_sample.py",
        "pilot_snapshot": study / "PILOT_SNAPSHOT_v1.json",
    }
    if set(study_lock["sha256"]) != set(paths):
        raise ValueError("Frozen study lock file set changed")
    for name, path in paths.items():
        if sha(path) != study_lock["sha256"][name]:
            raise ValueError(f"Frozen study source hash changed: {name}")
    protocol_lock = read_json(evals / "PROTOCOL.lock.json")
    label_lock = read_json(evals / "labels/followup_labels.lock.json")
    if (
        sha(paths["v1_labels"]) != protocol_lock["labels_sha256"]
        or label_lock["labels_sha256"] != protocol_lock["labels_sha256"]
        or sha(paths["v1_labels_frozen"]) != label_lock["frozen_copy_sha256"]
    ):
        raise ValueError("Frozen human-label locks disagree")
    for relative, digest in protocol_lock["files_sha256"].items():
        if sha(evals / relative) != digest:
            raise ValueError(f"Frozen v1.0 protocol source changed: {relative}")
    pilot = read_json(study / "PILOT_SNAPSHOT_v1.json")
    pilot_dir = evals / pilot["pilot_directory"]
    if {path.name for path in pilot_dir.iterdir() if path.is_file()} != set(pilot["file_sha256"]):
        raise ValueError("Original pilot file set changed")
    for name, digest in pilot["file_sha256"].items():
        if sha(pilot_dir / name) != digest:
            raise ValueError(f"Original pilot output hash changed: {name}")


def _verify_source_reports(source_lock: dict, inventory: dict) -> dict[str, dict]:
    progress = REPO / "backend/evals/results/20261011T223751Z-final/progress.jsonl"
    reports = {}
    with progress.open(encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            if item["kind"] != "persona":
                continue
            row = item["row"]
            report_id = row["persona_id"]
            if report_id in reports:
                raise ValueError(f"Duplicate source report: {report_id}")
            digest = hashlib.sha256(
                json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8"
                )
            ).hexdigest()
            if source_lock["persona_report_sha256"].get(report_id) != digest:
                raise ValueError(f"Source report hash changed: {report_id}")
            reports[report_id] = row
    if set(reports) != set(source_lock["persona_report_sha256"]) or len(reports) != 15:
        raise ValueError("Source report set differs from source lock")
    checks = {row["persona_id"]: row for row in inventory["calculation_checks"]}
    if set(checks) != set(reports):
        raise ValueError("Overall-score check report set changed")
    for report_id, row in reports.items():
        by_category = defaultdict(list)
        for assessment in row["report"]["question_evaluations"]:
            if assessment["score"] is not None:
                category = assessment["category"]
                if category not in WEIGHTS:
                    raise ValueError(f"Unexpected scoring category: {category}")
                by_category[category].append(float(assessment["score"]))
        if not by_category:
            computed = 0.0
        else:
            total_weight = sum(WEIGHTS[name] for name in by_category)
            computed = round(
                sum(
                    WEIGHTS[name] * sum(values) / len(values)
                    for name, values in by_category.items()
                )
                / total_weight,
                4,
            )
        recommendation = next(
            (name for threshold, name in THRESHOLDS if computed >= threshold), "no_hire"
        )
        if (
            abs(computed - float(row["report"]["overall_score"])) > 0.00001
            or abs(computed - float(row["score"])) > 0.00001
            or abs(computed - float(checks[report_id]["overall_score"])) > 0.00001
            or any(
                value != recommendation
                for value in (
                    row["report"]["recommendation"],
                    row["recommendation"],
                    checks[report_id]["recommendation"],
                )
            )
        ):
            raise ValueError(f"Overall-score arithmetic mismatch: {report_id}")
    return reports


def verify_inputs() -> tuple[list[dict], list[dict], dict]:
    """Validate every frozen input and review before any result calculation."""
    if sha(LOCK) != LOCK_SHA256:
        raise ValueError("Completed score-review lock hash changed")
    lock = read_json(LOCK)
    if (
        lock["version"] != "1.1a"
        or lock["status"] != "completed_human_review_frozen_metrics_not_calculated"
        or lock["validated_assessments"] != 45
    ):
        raise ValueError("Completed score-review lock has unexpected status")
    reviewed_path = _locked_path(lock, "completed_review")
    release_path = _locked_path(lock, "release_lock")
    released_path = _locked_path(lock, "released_sheet")
    manifest_path = _locked_path(lock, "release_manifest")
    _locked_path(lock, "addendum")
    manifest, release_lock = read_json(manifest_path), read_json(release_path)
    if (
        manifest["version"] != "1.1a"
        or release_lock["version"] != "1.1a"
        or manifest["validation"]["score_rows"] != 45
        or manifest["validation"]["adopted_claim_rows"] != 245
        or manifest["score_sheet_sha256_at_release"] != sha(released_path)
    ):
        raise ValueError("Release provenance changed")
    for path, digest in {**manifest["input_sha256"], **release_lock["sha256"]}.items():
        if sha(REPO / path) != digest:
            raise ValueError(f"Frozen source hash changed: {path}")
    _verify_upstream_locks()
    source_lock = read_json(STUDY / "source.lock.json")
    inventory_path = STUDY / "inventory.json"
    if (
        source_lock["source_run_status"] != "incomplete"
        or sha(inventory_path) != source_lock["inventory_sha256"]
    ):
        raise ValueError("Source-locked inventory changed")
    inventory = read_json(inventory_path)
    if (
        len(inventory["claims"]) != 245
        or len(inventory["scores"]) != 45
        or len(inventory["calculation_checks"]) != 15
    ):
        raise ValueError("Source inventory row counts changed")
    reports = _verify_source_reports(source_lock, inventory)
    adopted_path = HERE / "human_review" / "intermind_final_user_adjudicated_245.csv"
    if sha(adopted_path) != manifest["input_sha256"][adopted_path.relative_to(REPO).as_posix()]:
        raise ValueError("Adopted claim review hash changed")
    fields, claims = read_csv(adopted_path)
    if not {"claim_id", "claim_text", "full_candidate_answer", "final_human_verdict"} <= set(
        fields
    ):
        raise ValueError("Adopted claim review columns changed")
    source_claims = {item["claim_id"]: item for item in inventory["claims"]}
    ids = [row["claim_id"] for row in claims]
    if (
        len(claims) != 245
        or len(source_claims) != 245
        or len(set(ids)) != 245
        or set(ids) != set(source_claims)
    ):
        raise ValueError("Adopted claim IDs differ from source inventory")
    for row in claims:
        source = source_claims[row["claim_id"]]
        if (
            row["final_human_verdict"] not in CLAIM_VERDICTS
            or row["claim_text"] != source["claim_text"]
            or row["full_candidate_answer"] != source["full_candidate_answer"]
        ):
            raise ValueError(f"Adopted claim changed: {row['claim_id']}")
    original_fields, original = read_csv(released_path)
    reviewed_fields, reviewed = read_csv(reviewed_path)
    expected_fields = manifest["score_sheet_fields"]
    if original_fields != expected_fields or reviewed_fields != expected_fields:
        raise ValueError("Score review columns changed")
    source_scores = {item["score_review_id"]: item for item in inventory["scores"]}
    original_ids = [row["score_review_id"] for row in original]
    reviewed_ids = [row["score_review_id"] for row in reviewed]
    if (
        len(original) != 45
        or len(reviewed) != 45
        or len(source_scores) != 45
        or len(set(reviewed_ids)) != 45
        or original_ids != reviewed_ids
        or set(reviewed_ids) != set(source_scores)
    ):
        raise ValueError("Score assessment IDs or order changed")
    sample = read_json(REPO / "backend/evals/claim_validity/SAMPLE_v1.json")
    selected = {(item["job_id"], item["category"], item["target"]) for item in sample["targets"]}
    if len(selected) != 15:
        raise ValueError("Frozen target sample changed")
    for index, (source_row, row) in enumerate(zip(original, reviewed, strict=True)):
        inv = source_scores[row["score_review_id"]]
        if (
            row["report_id"] not in reports
            or (row["job_id"], row["category"], row["target"]) not in selected
            or row["report_id"] != inv["report_id"]
        ):
            raise ValueError(f"Score source identity changed: {index + 1}")
        for field in expected_fields:
            if field not in JUDGMENT_FIELDS and row[field] != source_row[field]:
                raise ValueError(f"Score source field changed: {index + 1} {field}")
        for field in (
            "target",
            "score",
            "band",
            "evidence_strings",
            "strengths",
            "weaknesses",
            "full_candidate_answer",
            "question",
        ):
            if str(inv[field]) != row[field]:
                raise ValueError(f"Inventory score field changed: {index + 1} {field}")
        if (
            row["verdict"] not in SCORE_VERDICTS
            or row["material_omission"] not in OMISSIONS
            or (row["verdict"] != "DEFENSIBLE" and not row["note"].strip())
            or (row["material_omission"] != "NO" and not row["omission_detail"].strip())
        ):
            raise ValueError(f"Invalid score review judgment: {index + 1}")
    verdicts = Counter(row["verdict"] for row in reviewed)
    omissions = Counter(row["material_omission"] for row in reviewed)
    if dict(verdicts) != {
        key: value for key, value in lock["verdict_counts"].items() if value
    } or dict(omissions) != {
        key: value for key, value in lock["material_omission_counts"].items() if value
    }:
        raise ValueError("Completed score-review counts disagree with lock")
    if set(item["report_id"] for item in inventory["claims"]) != set(reports) or Counter(
        row["report_id"] for row in reviewed
    ) != Counter({key: 3 for key in reports}):
        raise ValueError("Report distribution changed")
    return claims, reviewed, inventory


def percentage(count: int, total: int) -> float:
    return round(100 * count / total, 2) if total else 0.0


def distribution(rows: list[dict], field: str, options: tuple[str, ...]) -> dict:
    counts = Counter(row[field] for row in rows)
    return {
        "n": len(rows),
        "counts": {name: counts[name] for name in options},
        "percent": {name: percentage(counts[name], len(rows)) for name in options},
    }


def _percentile(values: list[float], proportion: float) -> float:
    ordered = sorted(values)
    position = proportion * (len(ordered) - 1)
    low = int(position)
    fraction = position - low
    return ordered[low] * (1 - fraction) + ordered[min(low + 1, len(ordered) - 1)] * fraction


def cluster_sensitivity(
    per_report: list[dict], *, draws: int = 10000, seed: int = 20261013
) -> dict:
    """Fixed-job report-cluster resampling; descriptive, not a population CI."""
    if draws < 2:
        raise ValueError("At least two resamples required")
    by_job = defaultdict(list)
    for report in per_report:
        by_job[report["job_id"]].append(report)
    if len(by_job) != 5 or any(len(items) != 3 for items in by_job.values()):
        raise ValueError("Expected three report clusters in each of five jobs")
    metrics = ("claim_supported_fraction", "score_defensible_fraction", "omission_yes_fraction")
    samples = {name: [] for name in metrics}
    rng = random.Random(seed)
    for _ in range(draws):
        selected = [rng.choice(by_job[job]) for job in sorted(by_job) for _ in range(3)]
        for name in metrics:
            samples[name].append(sum(row[name] for row in selected) / 15)
    return {
        "method": "stratified_report_cluster_bootstrap_descriptive_only",
        "seed": seed,
        "draws": draws,
        "interval_percentiles": [2.5, 97.5],
        "intervals": {
            name: [
                round(100 * _percentile(values, 0.025), 2),
                round(100 * _percentile(values, 0.975), 2),
            ]
            for name, values in samples.items()
        },
    }


def analyze(claims: list[dict], scores: list[dict], inventory: dict) -> dict:
    claim_inventory = {item["claim_id"]: item for item in inventory["claims"]}
    by_report_claims = defaultdict(list)
    by_report_scores = defaultdict(list)
    for row in claims:
        by_report_claims[claim_inventory[row["claim_id"]]["report_id"]].append(row)
    for row in scores:
        by_report_scores[row["report_id"]].append(row)
    per_report = []
    for report_id in sorted(by_report_scores):
        report_claims, report_scores = by_report_claims[report_id], by_report_scores[report_id]
        if not report_claims or len(report_scores) != 3:
            raise ValueError(f"Incomplete review cluster: {report_id}")
        per_report.append(
            {
                "report_id": report_id,
                "job_id": report_scores[0]["job_id"],
                "persona_tier": claim_inventory[report_claims[0]["claim_id"]]["persona_tier"],
                "claims": distribution(report_claims, "final_human_verdict", CLAIM_VERDICTS),
                "scores": distribution(report_scores, "verdict", SCORE_VERDICTS),
                "omissions": distribution(report_scores, "material_omission", OMISSIONS),
                "claim_supported_fraction": sum(
                    row["final_human_verdict"] == "SUPPORTED" for row in report_claims
                )
                / len(report_claims),
                "score_defensible_fraction": sum(
                    row["verdict"] == "DEFENSIBLE" for row in report_scores
                )
                / 3,
                "omission_yes_fraction": sum(
                    row["material_omission"] == "YES" for row in report_scores
                )
                / 3,
            }
        )
    if len(per_report) != 15:
        raise ValueError("Expected 15 review clusters")
    by_job = defaultdict(list)
    for report in per_report:
        by_job[report["job_id"]].append(report)
    per_job = []
    for job_id, reports in sorted(by_job.items()):
        job_claims = [row for report in reports for row in by_report_claims[report["report_id"]]]
        job_scores = [row for report in reports for row in by_report_scores[report["report_id"]]]
        per_job.append(
            {
                "job_id": job_id,
                "reports": len(reports),
                "claims": distribution(job_claims, "final_human_verdict", CLAIM_VERDICTS),
                "scores": distribution(job_scores, "verdict", SCORE_VERDICTS),
                "omissions": distribution(job_scores, "material_omission", OMISSIONS),
                "mean_report_claim_supported_percent": round(
                    100 * sum(row["claim_supported_fraction"] for row in reports) / len(reports), 2
                ),
                "mean_report_score_defensible_percent": round(
                    100 * sum(row["score_defensible_fraction"] for row in reports) / len(reports), 2
                ),
            }
        )
    by_target = defaultdict(list)
    by_band = defaultdict(list)
    for row in scores:
        by_target[(row["job_id"], row["category"], row["target"])].append(row)
        by_band[row["band"]].append(row)
    per_target = [
        {
            "job_id": job,
            "category": category,
            "target": target,
            "scores": distribution(rows, "verdict", SCORE_VERDICTS),
            "omissions": distribution(rows, "material_omission", OMISSIONS),
        }
        for (job, category, target), rows in sorted(by_target.items())
    ]
    per_band = [
        {
            "band": band,
            "scores": distribution(rows, "verdict", SCORE_VERDICTS),
            "omissions": distribution(rows, "material_omission", OMISSIONS),
        }
        for band, rows in sorted(by_band.items())
    ]
    bad = [row for row in scores if row["verdict"] == "NOT_DEFENSIBLE"]
    return {
        "version": "1.1a",
        "source_run_status": "incomplete_recovered",
        "provenance": "one_human_reviewer_adopted_AI_assisted_final_judgments",
        "claims": distribution(claims, "final_human_verdict", CLAIM_VERDICTS),
        "scores": distribution(scores, "verdict", SCORE_VERDICTS),
        "material_omissions": distribution(scores, "material_omission", OMISSIONS),
        "primary_report_mean_percent": {
            "claim_supported": round(
                100 * sum(row["claim_supported_fraction"] for row in per_report) / 15, 2
            ),
            "score_defensible": round(
                100 * sum(row["score_defensible_fraction"] for row in per_report) / 15, 2
            ),
        },
        "job_mean_range_percent": {
            "claim_supported": [
                min(row["mean_report_claim_supported_percent"] for row in per_job),
                max(row["mean_report_claim_supported_percent"] for row in per_job),
            ],
            "score_defensible": [
                min(row["mean_report_score_defensible_percent"] for row in per_job),
                max(row["mean_report_score_defensible_percent"] for row in per_job),
            ],
        },
        "descriptive_report_cluster_sensitivity": cluster_sensitivity(per_report),
        "per_report": per_report,
        "per_job": per_job,
        "per_target": per_target,
        "per_score_band": per_band,
        "not_defensible_assessments": [
            {
                key: row[key]
                for key in (
                    "score_review_id",
                    "report_id",
                    "job_id",
                    "category",
                    "target",
                    "score",
                    "band",
                    "question",
                    "full_candidate_answer",
                    "note",
                    "material_omission",
                    "omission_detail",
                )
            }
            for row in bad
        ],
        "overall_score_and_recommendation_arithmetic_checked_reports": 15,
        "limitations": [
            "Retrospective v1.1a deviation: no documented independent pre-AI initial "
            "human claim or score review and no original initial-claim lock.",
            "Final verdicts were adopted by one human after AI assistance; AI outputs "
            "are not independent human raters or human inter-rater reliability.",
            "Claims and score assessments cluster within 15 reports; authored jobs "
            "and personas are purposive, not a random applicant sample.",
            "The source v1.0 run was incomplete and per-request model provenance "
            "for recovered reports is missing.",
            "The report-cluster intervals are descriptive resampling sensitivity, "
            "not population confidence or reviewer-uncertainty intervals.",
            "Band defensibility is not numeric score accuracy; these results do "
            "not measure predictive hiring validity.",
        ],
    }


def render_report(metrics: dict) -> str:
    claims, scores, omissions = (
        metrics[name] for name in ("claims", "scores", "material_omissions")
    )
    primary = metrics["primary_report_mean_percent"]
    intervals = metrics["descriptive_report_cluster_sensitivity"]["intervals"]
    lines = [
        "# Internal Claim & Score Validity results, v1.1a",
        "",
        "These are retrospective, reviewer-adopted judgments over recovered reports. "
        "The source v1.0 run was incomplete. This report is internal and does not "
        "amend the frozen protocol.",
        "",
        "## Separate results",
        "",
        "| Measure | Counts | Pooled percentages | Report mean | "
        "Descriptive report-cluster interval |",
        "| --- | --- | --- | ---: | ---: |",
        f"| Fully supported claims | {claims['counts']['SUPPORTED']}/{claims['n']} | "
        f"{claims['percent']['SUPPORTED']}% | {primary['claim_supported']}% | "
        f"{intervals['claim_supported_fraction'][0]}–{intervals['claim_supported_fraction'][1]}% |",
        f"| Defensible score bands | {scores['counts']['DEFENSIBLE']}/{scores['n']} | "
        f"{scores['percent']['DEFENSIBLE']}% | {primary['score_defensible']}% | "
        f"{intervals['score_defensible_fraction'][0]}–"
        f"{intervals['score_defensible_fraction'][1]}% |",
        f"| Material omissions marked YES | {omissions['counts']['YES']}/{omissions['n']} | "
        f"{omissions['percent']['YES']}% | — | "
        f"{intervals['omission_yes_fraction'][0]}–{intervals['omission_yes_fraction'][1]}% |",
        "",
        "Claim verdicts: "
        + ", ".join(
            f"{name} {claims['counts'][name]} ({claims['percent'][name]}%)"
            for name in CLAIM_VERDICTS
        )
        + ".",
        "Score verdicts: "
        + ", ".join(
            f"{name} {scores['counts'][name]} ({scores['percent'][name]}%)"
            for name in SCORE_VERDICTS
        )
        + ".",
        "Material omissions: "
        + ", ".join(
            f"{name} {omissions['counts'][name]} ({omissions['percent'][name]}%)"
            for name in OMISSIONS
        )
        + ".",
        "",
        "The primary claim and score percentages are means of 15 report fractions. "
        "The fixed-job report-cluster bootstrap (10,000 draws, seed 20261013) gives only "
        "a descriptive sensitivity interval; it does not support population inference.",
        "",
        "## By job (three authored reports per job)",
        "",
        "| Job | Claims supported | Mean report claim % | Score bands defensible | Omissions YES |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in metrics["per_job"]:
        lines.append(
            f"| {row['job_id']} | {row['claims']['counts']['SUPPORTED']}/{row['claims']['n']} | "
            f"{row['mean_report_claim_supported_percent']} | "
            f"{row['scores']['counts']['DEFENSIBLE']}/{row['scores']['n']} | "
            f"{row['omissions']['counts']['YES']}/{row['omissions']['n']} |"
        )
    job_range = metrics["job_mean_range_percent"]
    lines += [
        "",
        "Across the five jobs, mean report claim support ranges from "
        f"{job_range['claim_supported'][0]}% to {job_range['claim_supported'][1]}%; "
        "mean report score-band defensibility ranges from "
        f"{job_range['score_defensible'][0]}% to {job_range['score_defensible'][1]}%.",
    ]
    lines += [
        "",
        "## By report (three score assessments each)",
        "",
        "| Report | Claims supported | Score bands defensible | Omissions YES |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in metrics["per_report"]:
        lines.append(
            f"| {row['report_id']} | {row['claims']['counts']['SUPPORTED']}/{row['claims']['n']} | "
            f"{row['scores']['counts']['DEFENSIBLE']}/3 | "
            f"{row['omissions']['counts']['YES']}/3 |"
        )
    lines += [
        "",
        "## By preselected target (three personas per target; small sample)",
        "",
        "| Job | Category | Target | Defensible | Omissions YES |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for row in metrics["per_target"]:
        lines.append(
            f"| {row['job_id']} | {row['category']} | {row['target']} | "
            f"{row['scores']['counts']['DEFENSIBLE']}/3 | "
            f"{row['omissions']['counts']['YES']}/3 |"
        )
    lines += [
        "",
        "## By assigned score band (small and uneven groups)",
        "",
        "| Band | Defensible | Omissions YES |",
        "| --- | ---: | ---: |",
    ]
    for row in metrics["per_score_band"]:
        lines.append(
            f"| {row['band']} | {row['scores']['counts']['DEFENSIBLE']}/{row['scores']['n']} | "
            f"{row['omissions']['counts']['YES']}/{row['omissions']['n']} |"
        )
    lines += ["", "## Not defensible assessment", ""]
    for row in metrics["not_defensible_assessments"]:
        lines.append(
            f"- `{row['score_review_id']}` ({row['report_id']}, {row['target']}, "
            f"score {row['score']}, {row['band']}): {row['note']} "
            f"Material omission: {row['omission_detail']}"
        )
    lines += [
        "",
        "## Verification and limits",
        "",
        "All 15 overall-score and recommendation calculations matched the recovered reports. "
        "The completed review, adopted claims, release chain, source inventory "
        "and report hashes were checked before aggregation.",
        "",
    ]
    lines += [f"- {item}" for item in metrics["limitations"]]
    return "\n".join(lines) + "\n"


def run(out_dir: Path = RESULTS) -> dict:
    if out_dir.exists():
        raise FileExistsError(f"Results already exist: {out_dir}")
    claims, scores, inventory = verify_inputs()
    metrics = analyze(claims, scores, inventory)
    if out_dir.exists():
        raise FileExistsError(f"Results already exist: {out_dir}")
    with tempfile.TemporaryDirectory(prefix=".claim_score_results_", dir=out_dir.parent) as temp:
        temp_dir = Path(temp)
        metrics_path = temp_dir / "metrics.json"
        report_path = temp_dir / "RESULTS.md"
        metrics_path.write_text(
            json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        report_path.write_text(render_report(metrics), encoding="utf-8")
        lock = {
            "version": "1.1a",
            "status": "offline_retrospective_results_locked",
            "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "source_run_status": "incomplete_recovered",
            "inputs_sha256": {
                str(LOCK.relative_to(REPO)).replace("\\", "/"): sha(LOCK),
                str(
                    (HERE / "human_review/intermind_final_user_adjudicated_245.csv").relative_to(
                        REPO
                    )
                ).replace("\\", "/"): sha(
                    HERE / "human_review/intermind_final_user_adjudicated_245.csv"
                ),
                str(
                    (HERE / "human_review/intermind_final_score_review_45.csv").relative_to(REPO)
                ).replace("\\", "/"): sha(
                    HERE / "human_review/intermind_final_score_review_45.csv"
                ),
                str((STUDY / "inventory.json").relative_to(REPO)).replace("\\", "/"): sha(
                    STUDY / "inventory.json"
                ),
                str(Path(__file__).relative_to(REPO)).replace("\\", "/"): sha(Path(__file__)),
            },
            "outputs_sha256": {"metrics.json": sha(metrics_path), "RESULTS.md": sha(report_path)},
            "n_claims": 245,
            "n_score_assessments": 45,
            "n_reports": 15,
        }
        lock_path = temp_dir / "RESULTS.lock.json"
        lock_path.write_text(
            json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        for path in (metrics_path, report_path, lock_path):
            os.chmod(path, 0o444)
        os.rename(temp_dir, out_dir)
    return metrics


if __name__ == "__main__":
    result = run()
    print(
        json.dumps(
            {
                "output": str(RESULTS),
                "claims": result["claims"],
                "scores": result["scores"],
                "material_omissions": result["material_omissions"],
            },
            indent=2,
        )
    )
