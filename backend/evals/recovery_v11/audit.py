"""Offline audit of the interrupted v1.0 run. Never edits its source files."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

from app.domain.evaluation import AnswerEvaluation, resolve_follow_up_decision
from app.domain.report import InterviewReport
from evals.claim_validity.study import extract_inventory, require_study_lock
from evals.datasets.evaluation import followup_cases, personas
from evals.harness.grounding import classify
from evals.recovery_v11.provenance_v12 import (
    historical_source_path,
    verify_historical_provenance,
)
from evals.run_interview_eval import _require_frozen_labels, _require_frozen_protocol

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results" / "20261011T223751Z-final"
OUTPUT = Path(__file__).resolve().parent / "artifacts" / "20261011T223751Z"


def sha(path: Path) -> str:
    return hashlib.sha256(historical_source_path(path).read_bytes()).hexdigest()


def progress() -> dict[str, list[dict]]:
    rows: dict[str, list[dict]] = {"followup": [], "persona": [], "latency": []}
    for line in (SOURCE / "progress.jsonl").read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if set(item) != {"kind", "row"} or item["kind"] not in rows:
            raise ValueError("Unexpected progress row")
        rows[item["kind"]].append(item["row"])
    return rows


def audit() -> tuple[dict, list[dict]]:
    verify_historical_provenance()
    protocol = _require_frozen_protocol()
    _require_frozen_labels()
    require_study_lock()  # Also checks the nine original pilot output hashes.
    state = json.loads((SOURCE / "run_state.json").read_text(encoding="utf-8"))
    if state.get("status") != "incomplete" or set(SOURCE.iterdir()) != {
        SOURCE / "progress.jsonl", SOURCE / "run_state.json"
    }:
        raise ValueError("Source run state or file set changed")
    rows = progress()
    cases = {case.case_id: case for case in followup_cases.CASES}
    followups = rows["followup"]
    ids = [row["case_id"] for row in followups]
    if len(ids) != 90 or len(set(ids)) != 90 or set(ids) != set(cases):
        raise ValueError("Follow-up IDs are missing, duplicated, or unknown")
    for row in followups:
        raw = AnswerEvaluation.model_validate(row["raw_evaluation"])
        case = cases[row["case_id"]]
        decision = resolve_follow_up_decision(
            raw, follow_ups_used=1 if case.prior_exchange else 0
        )
        if row["prediction"] != decision.decision.value:
            raise ValueError(f"Policy prediction mismatch: {case.case_id}")
    reports = rows["persona"]
    for row in reports:
        InterviewReport.model_validate(row["report"])
    inventory = extract_inventory(reports)  # Checks all IDs, inputs and score arithmetic.
    candidates = {candidate.persona_id: candidate for candidate in personas.PERSONAS}
    evidence: list[dict] = []
    review: list[dict] = []
    for row in reports:
        candidate = candidates[row["persona_id"]]
        answers = list(candidate.answers)
        full_context = "\n\n".join(
            f"[{i + 1}] Q: {answer.question}\nA: {answer.answer}"
            for i, answer in enumerate(answers)
        )
        for question in row["report"]["question_evaluations"]:
            source_index = next(
                i for i, answer in enumerate(answers) if answer.target == question["target"]
            )
            for item in question["evidence"]:
                evidence_id = "ev-" + hashlib.sha256(
                    f"{candidate.persona_id}\0{question['target_id']}\0{item}".encode()
                ).hexdigest()[:20]
                matches = [
                    i + 1 for i, answer in enumerate(answers)
                    if classify(item, [answer.answer]).auto_supported
                ]
                target_tier = classify(item, [answers[source_index].answer]).tier.value
                if matches == [source_index + 1] and target_tier == "supported_exact":
                    status = "unique_target_exact"
                elif matches == [source_index + 1]:
                    status = "lexical_target_requires_review"
                elif len(matches) == 1:
                    status = "unique_other_source_requires_review"
                elif matches:
                    status = "ambiguous_sources"
                else:
                    status = "unattributable_automatically"
                record = {
                    "evidence_id": evidence_id, "report_id": candidate.persona_id,
                    "target_id": question["target_id"], "status": status,
                    "matching_answer_indices": matches, "evidence_string": item,
                }
                evidence.append(record)
                if status != "unique_target_exact":
                    review.append({
                        "evidence_id": evidence_id, "evidence_string": item,
                        "target_question": question["question"],
                        "target_answer": answers[source_index].answer,
                        "full_interview_context": full_context,
                        "source_answer_index": "", "verdict": "", "note": "",
                    })
    if len(evidence) != 239 or len({item["evidence_id"] for item in evidence}) != 239:
        raise ValueError("Unexpected evidence inventory or duplicate IDs")
    source_paths = [
        ROOT / "run_interview_eval.py", ROOT / "harness" / "evidence.py",
        ROOT / "harness" / "grounding.py", ROOT / "harness" / "metrics.py",
        ROOT.parent / "app" / "llm" / "openai_client.py",
        ROOT.parent / "app" / "domain" / "evaluation.py",
        ROOT.parent / "app" / "services" / "report_scoring.py",
        *(ROOT.parent / "app" / "llm" / "prompts" / name for name in (
            "answer_evaluation_v1.md", "interview_questions_v1.md", "interview_report_v1.md"
        )),
    ]
    manifest = {
        "version": "1.1", "source_status": "incomplete",
        "source_run": SOURCE.relative_to(ROOT).as_posix(),
        "source_files_sha256": {p.name: sha(p) for p in sorted(SOURCE.iterdir())},
        "frozen_files_sha256": protocol["files_sha256"],
        "frozen_labels_sha256": protocol["labels_sha256"],
        "study_v1_lock_sha256": sha(ROOT / "claim_validity" / "STUDY.lock.json"),
        "pilot_snapshot_sha256": sha(ROOT / "claim_validity" / "PILOT_SNAPSHOT_v1.json"),
        "source_code_sha256": {p.relative_to(ROOT.parent).as_posix(): sha(p)
                               for p in source_paths},
        "recovery_files_sha256": {
            name: sha(Path(__file__).parent / name) for name in (
                "audit.py", "ledger.py", "latency.py", "PROTOCOL_v1.1.md",
                "CLAIM_STUDY_v1.1.md", "REVIEW_GUIDE_v1.1.md",
                "PROTOCOL_v1.1.lock.json"
            )
        },
        "validated_followup_case_ids": ids,
        "validated_persona_report_ids": [row["persona_id"] for row in reports],
        "validation": {
            "followups": 90, "persona_reports": 15, "question_assessments": 150,
            "selected_claim_inventory": len(inventory["claims"]),
            "selected_score_assessments": len(inventory["scores"]),
            "report_score_calculations": len(inventory["calculation_checks"]),
            "evidence_strings": len(evidence),
            "evidence_attribution": dict(Counter(item["status"] for item in evidence)),
            "latency_requests_saved": len(rows["latency"]),
        },
        "missing_provenance": [
            "No per-call token usage, cached tokens, cost, or returned model IDs",
            "No saved request payload hashes or per-turn persona histories",
            "No v1.0 evidence_internal.json or completed-run metadata",
        ],
        "eligible_v1_final_metrics": False,
        "recovered_evidence_metric_ready": False,
        "reason": "Human review and a separately frozen recovery protocol are required.",
    }
    return manifest, review


def write_once() -> dict:
    manifest, review = audit()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    path = OUTPUT / "RECOVERY_MANIFEST_v1.1.json"
    with path.open("x", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2, ensure_ascii=False)
        file.write("\n")
    with (OUTPUT / "evidence_source_review_blind.csv").open(
        "x", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=list(review[0]) if review else [
            "evidence_id", "evidence_string", "target_question", "target_answer",
            "full_interview_context", "source_answer_index", "verdict", "note"
        ])
        writer.writeheader()
        writer.writerows(review)
    (OUTPUT / "RECOVERY_MANIFEST_v1.1.sha256").write_text(sha(path) + "\n", encoding="ascii")
    os.chmod(path, 0o444)
    os.chmod(OUTPUT / "RECOVERY_MANIFEST_v1.1.sha256", 0o444)
    return manifest


if __name__ == "__main__":
    print(json.dumps(write_once()["validation"], indent=2))
