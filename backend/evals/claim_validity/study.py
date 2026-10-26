"""Offline preparation and aggregation for Claim & Score Validity v1.0.

From backend/: python -m evals.claim_validity.study COMMAND [paths]
This module has no OpenAI client, network call, or production write path.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from evals.datasets.evaluation.personas import JOBS, PERSONAS

HERE = Path(__file__).resolve().parent
EVALS = HERE.parent
CLAIM_VERDICTS = {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "UNCLEAR"}
SCORE_VERDICTS = {"DEFENSIBLE", "NOT_DEFENSIBLE", "UNCLEAR"}
OMISSION_VERDICTS = {"YES", "NO", "UNCLEAR"}
CATEGORIES = ("technology", "competency", "task")
WEIGHTS = {"competency": .4, "technology": .4, "task": .2}
THRESHOLDS = ((.85, "strong_hire"), (.65, "hire"), (.45, "consider"))
CLAIM_FIELDS = ("claim_id", "job_context", "question", "full_candidate_answer",
                "claim_text", "report_location", "verdict", "note")
SCORE_FIELDS = ("score_review_id", "job_context", "question", "full_candidate_answer",
                "target", "score", "band", "evidence_strings", "strengths",
                "weaknesses", "verdict", "note", "material_omission", "omission_detail")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_csv(path: Path, fields: tuple[str, ...]) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(fields):
            raise ValueError(f"Unexpected CSV columns in {path.name}")
        return list(reader)


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def require_study_lock() -> dict:
    lock = read_json(HERE / "STUDY.lock.json")
    paths = {
        "PROTOCOL_v1.md": HERE / "PROTOCOL_v1.md",
        "RUBRIC_v1.md": HERE / "RUBRIC_v1.md",
        "SAMPLE_v1.json": HERE / "SAMPLE_v1.json",
        "study.py": HERE / "study.py",
        "v1_protocol": EVALS / "PROTOCOL.md",
        "v1_protocol_lock": EVALS / "PROTOCOL.lock.json",
        "v1_labels": EVALS / "labels" / "followup_blind.csv",
        "v1_labels_frozen": EVALS / "labels" / "followup_blind.frozen.csv",
        "v1_labels_lock": EVALS / "labels" / "followup_labels.lock.json",
        "personas": EVALS / "datasets" / "evaluation" / "personas.py",
        "personas_sample": EVALS / "datasets" / "evaluation" / "personas_sample.py",
        "pilot_snapshot": HERE / "PILOT_SNAPSHOT_v1.json",
    }
    if set(lock["sha256"]) != set(paths):
        raise ValueError("Study lock file list changed")
    for name, path in paths.items():
        if sha(path) != lock["sha256"][name]:
            raise ValueError(f"Frozen study/source hash changed: {name}")
    v1 = read_json(EVALS / "PROTOCOL.lock.json")
    labels = read_json(EVALS / "labels" / "followup_labels.lock.json")
    if sha(EVALS / "labels" / "followup_blind.csv") != v1["labels_sha256"]:
        raise ValueError("Frozen v1.0 source changed")
    for relative, digest in v1["files_sha256"].items():
        if sha(EVALS / relative) != digest:
            raise ValueError(f"Frozen v1.0 source changed: {relative}")
    if labels["labels_sha256"] != v1["labels_sha256"]:
        raise ValueError("Frozen label locks disagree")
    if sha(EVALS / "labels" / "followup_blind.frozen.csv") != labels["frozen_copy_sha256"]:
        raise ValueError("Frozen human-label copy changed")
    pilot = read_json(HERE / "PILOT_SNAPSHOT_v1.json")
    pilot_dir = EVALS / pilot["pilot_directory"]
    actual_names = {path.name for path in pilot_dir.iterdir() if path.is_file()}
    if actual_names != set(pilot["file_sha256"]):
        raise ValueError("Original pilot output file set changed")
    for name, digest in pilot["file_sha256"].items():
        if sha(pilot_dir / name) != digest:
            raise ValueError(f"Original pilot output changed: {name}")
    return lock


def selected_targets() -> dict[str, set[tuple[str, str]]]:
    sample = read_json(HERE / "SAMPLE_v1.json")
    frozen_hash = sha(EVALS / "datasets" / "evaluation" / "personas.py")
    if sample["dataset_sha256"] != frozen_hash:
        raise ValueError("Frozen persona dataset differs from sample")
    expected = []
    for job in JOBS:
        if len(job.cases) != 10:
            raise ValueError("A job no longer has ten frozen targets")
        for category in CATEGORIES:
            candidates = [row[1] for row in job.cases if row[0] == category]
            if not candidates:
                raise ValueError("Sample category missing")
            target = min(candidates, key=lambda value: hashlib.sha256(
                f"{job.jd_id}\0{category}\0{value}".encode()).hexdigest())
            expected.append({"job_id": job.jd_id, "category": category, "target": target})
    if sample["version"] != "1.0" or sample["targets"] != expected:
        raise ValueError("Preselected sample does not match deterministic rule")
    return {job.jd_id: {(item["category"], item["target"]) for item in expected
                        if item["job_id"] == job.jd_id} for job in JOBS}


def band(score: float) -> str:
    if score >= .8:
        return "strong"
    if score >= .6:
        return "moderate"
    if score >= .35:
        return "limited"
    return "insufficient"


def calculated_score_and_recommendation(questions: list[dict]) -> tuple[float, str]:
    by_category: dict[str, list[float]] = defaultdict(list)
    for item in questions:
        if item["score"] is not None:
            if item["category"] not in WEIGHTS:
                raise ValueError("Unknown scoring category")
            by_category[item["category"]].append(float(item["score"]))
    if not by_category:
        score = 0.0
    else:
        weight_sum = sum(WEIGHTS[category] for category in by_category)
        score = round(sum(WEIGHTS[category] * sum(values) / len(values)
                          for category, values in by_category.items()) / weight_sum, 4)
    recommendation = next((name for threshold, name in THRESHOLDS
                           if score >= threshold), "no_hire")
    return score, recommendation


def _id(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha256("\0".join(parts).encode()).hexdigest()[:20]


def _sentences(summary: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", summary.strip())
            if part.strip()]


def _add_claim(claims: list[dict], seen: dict[str, dict], persona, context: str,
               full_report_context: str, text: str, location: str,
               question: str, source: str) -> None:
    text = text.strip()
    if not text:
        return
    key = " ".join(text.split()).casefold()
    if key in seen:
        seen[key]["locations"].append(location)
        if seen[key]["full_candidate_answer"] != source:
            seen[key]["full_candidate_answer"] = full_report_context
            seen[key]["question"] = "Full interview"
        return
    claim = {"claim_id": _id("cl-", persona.persona_id, location, text),
             "report_id": persona.persona_id, "job_id": persona.jd_id,
             "persona_tier": persona.tier, "job_context": context,
             "question": question, "full_candidate_answer": source,
             "claim_text": text, "report_location": location,
             "locations": [location]}
    claims.append(claim)
    seen[key] = claim


def extract_inventory(rows: list[dict]) -> dict:
    """Validate the 15 final reports and extract fixed review units without model judgment."""
    sample = selected_targets()
    expected = {p.persona_id: p for p in PERSONAS}
    if len(rows) != 15 or {row["persona_id"] for row in rows} != set(expected):
        raise ValueError("Final reports must contain the 15 frozen personas once")
    if len({row["persona_id"] for row in rows}) != 15:
        raise ValueError("Duplicate persona report")
    by_job = {job.jd_id: job for job in JOBS}
    claims, scores, calculation_checks = [], [], []
    for row in sorted(rows, key=lambda item: item["persona_id"]):
        persona = expected[row["persona_id"]]
        if row["jd_id"] != persona.jd_id or row["tier"] != persona.tier:
            raise ValueError("Report persona metadata disagrees with frozen dataset")
        report = row["report"]
        if report["interview_id"] != persona.persona_id:
            raise ValueError("Report interview ID mismatch")
        questions = report["question_evaluations"]
        answer_by_target = {answer.target: answer for answer in persona.answers}
        expected_keys = {(case[0], case[1]) for case in by_job[persona.jd_id].cases}
        keys = [(q["category"], q["target"]) for q in questions]
        if len(questions) != 10 or len(set(keys)) != 10 or set(keys) != expected_keys:
            raise ValueError("Report questions differ from the frozen ten targets")
        for q in questions:
            answer = answer_by_target[q["target"]]
            if q["question"] != answer.question or q["candidate_answer"] != answer.answer:
                raise ValueError("Report question/answer differs from frozen source")
        computed, recommendation = calculated_score_and_recommendation(questions)
        if (abs(computed - float(report["overall_score"])) > 0.00001
                or recommendation != report["recommendation"]
                or abs(computed - float(row["score"])) > 0.00001
                or recommendation != row["recommendation"]):
            raise ValueError("Overall score or recommendation arithmetic mismatch")
        calculation_checks.append({"persona_id": persona.persona_id,
                                   "overall_score": computed,
                                   "recommendation": recommendation})
        job = by_job[persona.jd_id]
        context = f"{job.role_title}: {job.text}"
        full_report_context = "\n\n".join(
            f"Q: {answer.question}\nA: {answer.answer}" for answer in persona.answers)
        seen: dict[str, dict] = {}

        for index, q in enumerate(questions):
            if (q["category"], q["target"]) not in sample[persona.jd_id]:
                continue
            answer = answer_by_target[q["target"]]
            score_id = _id("sc-", persona.persona_id, q["category"], q["target"])
            scores.append({"score_review_id": score_id, "report_id": persona.persona_id,
                           "job_id": persona.jd_id, "persona_tier": persona.tier,
                           "job_context": context, "question": answer.question,
                           "full_candidate_answer": answer.answer, "target": q["target"],
                           "score": q["score"], "band": band(float(q["score"])),
                           "evidence_strings": json.dumps(q["evidence"], ensure_ascii=False),
                           "strengths": json.dumps(q["strengths"], ensure_ascii=False),
                           "weaknesses": json.dumps(q["weaknesses"], ensure_ascii=False)})
            for kind in ("strengths", "weaknesses"):
                for subindex, text in enumerate(q[kind]):
                    _add_claim(
                        claims, seen, persona, context, full_report_context, text,
                        f"report.question_evaluations[{index}].{kind}[{subindex}]",
                        answer.question, answer.answer,
                    )
        for index, sentence in enumerate(_sentences(report["summary"])):
            _add_claim(claims, seen, persona, context, full_report_context, sentence,
                       f"report.summary.sentence[{index}]", "Full interview",
                       full_report_context)
        for kind in ("strengths", "weaknesses"):
            for index, text in enumerate(report[kind]):
                _add_claim(claims, seen, persona, context, full_report_context, text,
                           f"report.{kind}[{index}]", "Full interview", full_report_context)
    if len(scores) != 45 or len({item["score_review_id"] for item in scores}) != 45:
        raise ValueError("Expected exactly 45 sampled target assessments")
    if not claims or len({item["claim_id"] for item in claims}) != len(claims):
        raise ValueError("Empty or duplicate claim inventory")
    random.Random(20261012).shuffle(claims)
    random.Random(20261013).shuffle(scores)
    return {"claims": claims, "scores": scores, "calculation_checks": calculation_checks}


def _require_final_run(result_dir: Path) -> tuple[list[dict], dict]:
    if not result_dir.is_dir():
        raise ValueError("Final result directory does not exist")
    state = read_json(result_dir / "run_state.json")
    metadata = read_json(result_dir / "metadata.json")
    if state.get("status") != "complete" or metadata.get("pool") != "final":
        raise ValueError("Only a complete final run is eligible; pilot is excluded")
    v1 = read_json(EVALS / "PROTOCOL.lock.json")
    if (metadata.get("protocol_sha256") != v1["files_sha256"]["PROTOCOL.md"]
            or metadata.get("labels_sha256") != v1["labels_sha256"]
            or metadata.get("dataset_sha256", {}).get("personas")
            != v1["files_sha256"]["datasets/evaluation/personas.py"]):
        raise ValueError("Final run provenance differs from frozen v1.0")
    return read_json(result_dir / "persona_reports.json"), metadata


def prepare(result_dir: Path, out_dir: Path) -> dict:
    require_study_lock()
    if (out_dir.resolve().is_relative_to(result_dir.resolve())
            or out_dir.resolve().is_relative_to((EVALS / "results").resolve())
            or out_dir.resolve().is_relative_to((EVALS / "labels").resolve())):
        raise ValueError("Study output must be separate from results and frozen labels")
    rows, metadata = _require_final_run(result_dir)
    inventory = extract_inventory(rows)
    if out_dir.exists():
        raise FileExistsError("Study output already exists; use a new directory")
    out_dir.mkdir(parents=True)
    write_json(out_dir / "inventory.json", inventory)
    claim_rows = [{field: item.get(field, "") for field in CLAIM_FIELDS}
                  for item in inventory["claims"]]
    write_csv(out_dir / "claims_initial_blind.csv", CLAIM_FIELDS, claim_rows)
    write_json(out_dir / "source.lock.json", {
        "study_lock_sha256": sha(HERE / "STUDY.lock.json"),
        "run_directory": str(result_dir.resolve()),
        "run_metadata_sha256": sha(result_dir / "metadata.json"),
        "reports_sha256": sha(result_dir / "persona_reports.json"),
        "inventory_sha256": sha(out_dir / "inventory.json"),
        "model_configured": metadata["model_configured"],
        "n_reports": 15, "n_target_assessments": 45,
        "n_claims": len(inventory["claims"]),
    })
    return {"n_reports": 15, "n_target_assessments": 45,
            "n_claims": len(inventory["claims"])}


def _source_inventory(out_dir: Path) -> dict:
    require_study_lock()
    lock = read_json(out_dir / "source.lock.json")
    result_dir = Path(lock["run_directory"])
    if (sha(HERE / "STUDY.lock.json") != lock["study_lock_sha256"]
            or sha(result_dir / "metadata.json") != lock["run_metadata_sha256"]
            or sha(result_dir / "persona_reports.json") != lock["reports_sha256"]
            or sha(out_dir / "inventory.json") != lock["inventory_sha256"]):
        raise ValueError("Study inputs changed after preparation")
    rows, _ = _require_final_run(result_dir)
    inventory = extract_inventory(rows)
    if inventory != read_json(out_dir / "inventory.json"):
        raise ValueError("Claim extraction is not reproducible")
    return inventory


def _exact_ids(rows: list[dict], expected: set[str], field: str) -> None:
    ids = [row[field] for row in rows]
    if len(ids) != len(expected) or len(set(ids)) != len(ids) or set(ids) != expected:
        raise ValueError(f"Missing, duplicate, or unknown {field} values")


def _unchanged_context(rows: list[dict], originals: list[dict], id_field: str,
                       editable: set[str]) -> None:
    _exact_ids(rows, {x[id_field] for x in originals}, id_field)
    source = {x[id_field]: x for x in originals}
    for row in rows:
        for field in row:
            if field not in editable and row[field] != str(source[row[id_field]].get(field, "")):
                raise ValueError(f"Review context changed: {id_field} {field}")


def _claim_rows(out_dir: Path, inventory: dict) -> list[dict]:
    claims = read_csv(out_dir / "claims_initial_blind.csv", CLAIM_FIELDS)
    _unchanged_context(claims, inventory["claims"], "claim_id", {"verdict", "note"})
    for row in claims:
        if row["verdict"] not in CLAIM_VERDICTS:
            raise ValueError("Missing or invalid initial claim verdict")
        if row["verdict"] != "SUPPORTED" and not row["note"].strip():
            raise ValueError("Non-supported claim needs a note")
    return claims


def _initial_rows(out_dir: Path, inventory: dict) -> tuple[list[dict], list[dict]]:
    claims = _claim_rows(out_dir, inventory)
    claim_lock = read_json(out_dir / "claims_initial.lock.json")
    if sha(out_dir / "claims_initial_blind.csv") != claim_lock["claims_initial_sha256"]:
        raise ValueError("Initial claim judgments changed after freezing")
    scores = read_csv(out_dir / "scores_initial.csv", SCORE_FIELDS)
    _unchanged_context(scores, inventory["scores"], "score_review_id",
                       {"verdict", "note", "material_omission", "omission_detail"})
    for row in scores:
        if (row["verdict"] not in SCORE_VERDICTS
                or row["material_omission"] not in OMISSION_VERDICTS):
            raise ValueError("Missing or invalid initial score/omission verdict")
        if row["verdict"] != "DEFENSIBLE" and not row["note"].strip():
            raise ValueError("Non-defensible or unclear score needs a note")
        if row["material_omission"] != "NO" and not row["omission_detail"].strip():
            raise ValueError("Material/unclear omission needs detail")
    return claims, scores


def freeze_claims(out_dir: Path) -> None:
    inventory = _source_inventory(out_dir)
    _claim_rows(out_dir, inventory)
    path = out_dir / "claims_initial.lock.json"
    if path.exists() or (out_dir / "scores_initial.csv").exists():
        raise FileExistsError("Initial claims already frozen or score sheet released")
    write_json(path, {"claims_initial_sha256": sha(out_dir / "claims_initial_blind.csv")})
    score_rows = [{field: item.get(field, "") for field in SCORE_FIELDS}
                  for item in inventory["scores"]]
    write_csv(out_dir / "scores_initial.csv", SCORE_FIELDS, score_rows)


def freeze_initial(out_dir: Path) -> None:
    inventory = _source_inventory(out_dir)
    _initial_rows(out_dir, inventory)
    path = out_dir / "initial.lock.json"
    if path.exists():
        raise FileExistsError("Initial human review is already frozen")
    write_json(path, {name: sha(out_dir / name) for name in
                      ("claims_initial.lock.json", "claims_initial_blind.csv",
                       "scores_initial.csv")})
    write_csv(out_dir / "claims_ai.csv",
              ("claim_id", "assistant", "suggested_verdict", "rationale"), [])
    write_csv(out_dir / "scores_ai.csv",
              ("score_review_id", "assistant", "suggested_verdict", "rationale"), [])
    write_csv(out_dir / "claims_final.csv",
              ("claim_id", "final_verdict", "ai_considered", "change_reason"),
              [{"claim_id": x["claim_id"], "final_verdict": "", "ai_considered": "",
                "change_reason": ""} for x in inventory["claims"]])
    write_csv(out_dir / "scores_final.csv",
              ("score_review_id", "final_verdict", "material_omission",
               "omission_detail", "ai_considered", "change_reason"),
              [{"score_review_id": x["score_review_id"], "final_verdict": "",
                "material_omission": "", "omission_detail": "", "ai_considered": "",
                "change_reason": ""} for x in inventory["scores"]])


def _final_rows(out_dir: Path, inventory: dict) -> tuple[list[dict], list[dict], dict]:
    initial_lock = read_json(out_dir / "initial.lock.json")
    for name, digest in initial_lock.items():
        if sha(out_dir / name) != digest:
            raise ValueError("Initial human review changed after freezing")
    initials, initial_scores = _initial_rows(out_dir, inventory)
    initial_claim_by_id = {x["claim_id"]: x for x in initials}
    initial_score_by_id = {x["score_review_id"]: x for x in initial_scores}
    ai_specs = (
        ("claims_ai.csv", ("claim_id", "assistant", "suggested_verdict", "rationale"),
         "claim_id", CLAIM_VERDICTS, set(initial_claim_by_id)),
        ("scores_ai.csv", ("score_review_id", "assistant", "suggested_verdict", "rationale"),
         "score_review_id", SCORE_VERDICTS, set(initial_score_by_id)),
    )
    assisted = {}
    for name, fields, id_field, allowed, ids in ai_specs:
        seen = set()
        assisted[id_field] = set()
        for row in read_csv(out_dir / name, fields):
            key = (row[id_field], row["assistant"])
            if (row[id_field] not in ids or row["assistant"] not in {"ChatGPT", "Gemini"}
                    or row["suggested_verdict"] not in allowed or not row["rationale"].strip()
                    or key in seen):
                raise ValueError("Invalid, duplicate, or undocumented AI suggestion")
            seen.add(key)
            assisted[id_field].add(row[id_field])
    claims = read_csv(out_dir / "claims_final.csv",
                      ("claim_id", "final_verdict", "ai_considered", "change_reason"))
    scores = read_csv(out_dir / "scores_final.csv",
                      ("score_review_id", "final_verdict", "material_omission",
                       "omission_detail", "ai_considered", "change_reason"))
    _exact_ids(claims, set(initial_claim_by_id), "claim_id")
    _exact_ids(scores, set(initial_score_by_id), "score_review_id")
    for row in claims:
        if row["final_verdict"] not in CLAIM_VERDICTS:
            raise ValueError("Missing or invalid final claim verdict")
        if row["ai_considered"] not in {"YES", "NO"}:
            raise ValueError("AI consideration must be YES or NO")
        if row["ai_considered"] == "YES" and row["claim_id"] not in assisted["claim_id"]:
            raise ValueError("AI assistance marked without a recorded suggestion")
        if (row["final_verdict"] != initial_claim_by_id[row["claim_id"]]["verdict"]
                and not row["change_reason"].strip()):
            raise ValueError("Changed claim verdict needs a reason")
    for row in scores:
        if (row["final_verdict"] not in SCORE_VERDICTS
                or row["material_omission"] not in OMISSION_VERDICTS
                or row["ai_considered"] not in {"YES", "NO"}):
            raise ValueError("Missing or invalid final score/omission verdict")
        if row["material_omission"] != "NO" and not row["omission_detail"].strip():
            raise ValueError("Final material/unclear omission needs detail")
        if (row["ai_considered"] == "YES"
                and row["score_review_id"] not in assisted["score_review_id"]):
            raise ValueError("AI assistance marked without a recorded suggestion")
        initial = initial_score_by_id[row["score_review_id"]]
        if ((row["final_verdict"] != initial["verdict"]
             or row["material_omission"] != initial["material_omission"])
                and not row["change_reason"].strip()):
            raise ValueError("Changed score or omission verdict needs a reason")
    return claims, scores, {"initial_claims": initials, "initial_scores": initial_scores,
                            "assisted_claims": assisted["claim_id"],
                            "assisted_scores": assisted["score_review_id"]}


def freeze_final(out_dir: Path) -> None:
    inventory = _source_inventory(out_dir)
    _final_rows(out_dir, inventory)
    path = out_dir / "final.lock.json"
    if path.exists():
        raise FileExistsError("Final human adjudication is already frozen")
    write_json(path, {name: sha(out_dir / name) for name in
                      ("initial.lock.json", "claims_ai.csv", "scores_ai.csv",
                       "claims_final.csv", "scores_final.csv")})


def aggregate(out_dir: Path) -> dict:
    inventory = _source_inventory(out_dir)
    final_lock = read_json(out_dir / "final.lock.json")
    for name, digest in final_lock.items():
        if sha(out_dir / name) != digest:
            raise ValueError("Frozen review file changed")
    claims, scores, review = _final_rows(out_dir, inventory)
    claim_verdicts = {row["claim_id"]: row["final_verdict"] for row in claims}
    score_verdicts = {row["score_review_id"]: row["final_verdict"] for row in scores}
    by_report_claims: dict[str, list[str]] = defaultdict(list)
    for item in inventory["claims"]:
        by_report_claims[item["report_id"]].append(claim_verdicts[item["claim_id"]])
    by_report_scores: dict[str, list[str]] = defaultdict(list)
    for item in inventory["scores"]:
        by_report_scores[item["report_id"]].append(score_verdicts[item["score_review_id"]])
    if len(by_report_claims) != 15 or len(by_report_scores) != 15:
        raise ValueError("Every report needs reviewed claims and scores")
    report_rates = {key: values.count("SUPPORTED") / len(values)
                    for key, values in by_report_claims.items()}
    score_rates = {key: values.count("DEFENSIBLE") / len(values)
                   for key, values in by_report_scores.items()}
    report_to_job = {p.persona_id: p.jd_id for p in PERSONAS}
    report_to_tier = {p.persona_id: p.tier for p in PERSONAS}
    by_job = {job.jd_id: sum(report_rates[p] for p in report_rates
                             if report_to_job[p] == job.jd_id) / 3 for job in JOBS}
    by_tier = {tier: sum(report_rates[p] for p in report_rates
                         if report_to_tier[p] == tier) / 5
               for tier in ("strong", "mixed", "weak")}
    score_by_job = {job.jd_id: sum(score_rates[p] for p in score_rates
                                   if report_to_job[p] == job.jd_id) / 3 for job in JOBS}
    score_by_tier = {tier: sum(score_rates[p] for p in score_rates
                               if report_to_tier[p] == tier) / 5
                     for tier in ("strong", "mixed", "weak")}
    initial_claims = {x["claim_id"]: x["verdict"] for x in review["initial_claims"]}
    initial_scores = {x["score_review_id"]: x for x in review["initial_scores"]}
    output = {
        "study_version": "1.0", "human_reviewers": 1,
        "ai_assistance_is_not_human_review": True,
        "n_reports": 15, "n_target_assessments": len(scores),
        "claims": {"n": len(claims), "verdict_counts": dict(Counter(claim_verdicts.values())),
                   "mean_report_fully_supported_rate": sum(report_rates.values()) / 15,
                   "report_claim_counts": {
                       key: len(value) for key, value in by_report_claims.items()},
                   "per_job_mean_report_rate": by_job,
                   "per_tier_mean_report_rate": by_tier,
                   "job_rate_range": [min(by_job.values()), max(by_job.values())],
                   "changed_after_initial": sum(
                       row["final_verdict"] != initial_claims[row["claim_id"]]
                       for row in claims),
                   "ai_assisted_items": len(review["assisted_claims"])},
        "score_bands": {"n": len(scores), "verdict_counts": dict(Counter(score_verdicts.values())),
                        "mean_report_defensible_rate": sum(score_rates.values()) / 15,
                        "per_job_mean_report_rate": score_by_job,
                        "per_tier_mean_report_rate": score_by_tier,
                        "job_rate_range": [min(score_by_job.values()),
                                           max(score_by_job.values())],
                        "changed_after_initial": sum(
                            row["final_verdict"] != initial_scores[
                                row["score_review_id"]]["verdict"]
                            for row in scores),
                        "ai_assisted_items": len(review["assisted_scores"])},
        "material_omissions": dict(Counter(row["material_omission"] for row in scores)),
        "deterministic_calculation_checks": {"n": len(inventory["calculation_checks"]),
                                             "passed": len(inventory["calculation_checks"])},
        "limitations": [
            "One human reviewer; optional ChatGPT/Gemini suggestions are not "
            "independent human labels.",
            "Authored personas and five jobs are not a random sample of real applicants.",
            "Only three of ten targets per report are sampled for target-level review.",
            "Claim units are list items or sentences; compound assertions may remain in one unit.",
            "Repeated claims within reports and shared job context prevent "
            "independent-claim inference.",
            "Score-band defensibility is not numeric score accuracy or human ground-truth scoring.",
            "Report and job rates are descriptive; no population confidence interval is claimed.",
        ],
    }
    path = out_dir / "metrics.json"
    if path.exists():
        raise FileExistsError("Study metrics already exist")
    write_json(path, output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare").add_argument("result_dir", type=Path)
    commands.choices["prepare"].add_argument("study_dir", type=Path)
    for name in ("freeze-claims", "freeze-initial", "freeze-final", "aggregate"):
        commands.add_parser(name).add_argument("study_dir", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.result_dir, args.study_dir)
        print(json.dumps(result, indent=2))
    elif args.command == "freeze-claims":
        freeze_claims(args.study_dir)
        print("Initial claim judgments frozen; score sheet released")
    elif args.command == "freeze-initial":
        freeze_initial(args.study_dir)
        print("Initial human reviews frozen")
    elif args.command == "freeze-final":
        freeze_final(args.study_dir)
        print("Final human adjudication frozen")
    else:
        print(json.dumps(aggregate(args.study_dir), indent=2))


if __name__ == "__main__":
    main()
