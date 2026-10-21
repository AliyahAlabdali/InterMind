"""Offline v1.1 claim-study adapter for validated reports from the incomplete run.

This never changes the frozen v1.0 study or treats its source run as complete.
Run from backend/: python -m evals.recovery_v11.claim_study COMMAND [study_dir]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from evals.claim_validity import study
from evals.recovery_v11.audit import OUTPUT, SOURCE, sha
from evals.recovery_v11.followup_discrimination import PRIOR_SHA256, RESULTS, verify_inputs

STUDY_DIR = OUTPUT / "claim_validity_v1.1"
METHOD = Path(__file__).with_name("CLAIM_STUDY_v1.1.md")
RESULT_FILES = {
    "metrics.json": RESULTS / "metrics.json",
    "per_job.csv": RESULTS / "per_job.csv",
    "routing_overrides.csv": RESULTS / "routing_overrides.csv",
    "PROTOCOL.md": study.EVALS / "PROTOCOL.md",
    "PROTOCOL_v1.1.md": METHOD.with_name("PROTOCOL_v1.1.md"),
    "followup_blind.frozen.csv": study.EVALS / "labels" / "followup_blind.frozen.csv",
    "RECOVERY_MANIFEST_v1.1.json": OUTPUT / "RECOVERY_MANIFEST_v1.1.json",
    "progress.jsonl": SOURCE / "progress.jsonl",
    "run_state.json": SOURCE / "run_state.json",
    "FOLLOWUP_DISCRIMINATION_METHOD_v1.1.md": METHOD.with_name(
        "FOLLOWUP_DISCRIMINATION_METHOD_v1.1.md"
    ),
    "followup_discrimination.py": METHOD.with_name("followup_discrimination.py"),
}


def _canonical_hash(row: dict) -> str:
    import hashlib

    raw = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _blind_inventory(inventory: dict) -> dict:
    """Keep exact paths internally; show only neutral locations in Stage A."""
    claims = []
    for item in inventory["claims"]:
        match = re.match(r"report\.question_evaluations\[(\d+)\]", item["report_location"])
        area = f"target assessment {int(match.group(1)) + 1}" if match else "report-wide"
        claims.append({**item, "report_location": f"{area}; claim {item['claim_id']}"})
    return {**inventory, "claims": claims}


def validated_inventory() -> tuple[dict, dict]:
    """Recheck every upstream lock and every recovered report before extraction."""
    _, reports, _, manifest = verify_inputs()
    result_lock_path = RESULTS / "RESULT.lock.json"
    result_lock = study.read_json(result_lock_path)
    expected = dict(RESULT_FILES)
    expected.update({"prior:" + key: OUTPUT / key for key in PRIOR_SHA256})
    if (result_lock.get("version") != "1.1"
            or result_lock.get("source_status") != "incomplete"
            or set(result_lock["sha256"]) != set(expected)):
        raise ValueError("Prior recovered result lock has unexpected contents")
    for name, path in expected.items():
        if sha(path) != result_lock["sha256"][name]:
            raise ValueError(f"Prior recovered result changed: {name}")
    inventory = study.extract_inventory(reports)
    if (len(inventory["claims"]) != 245 or len(inventory["scores"]) != 45
            or len(inventory["calculation_checks"]) != 15
            or manifest["validation"]["selected_claim_inventory"] != 245
            or manifest["validation"]["selected_score_assessments"] != 45):
        raise ValueError("Recovered claim/score inventory differs from frozen audit")
    source = {
        "version": "1.1",
        "source_run_status": "incomplete",
        "recovery_manifest_sha256": sha(OUTPUT / "RECOVERY_MANIFEST_v1.1.json"),
        "source_progress_sha256": sha(SOURCE / "progress.jsonl"),
        "source_state_sha256": sha(SOURCE / "run_state.json"),
        "recovered_metrics_lock_sha256": sha(result_lock_path),
        "v1_study_lock_sha256": sha(study.HERE / "STUDY.lock.json"),
        "v1_sample_sha256": sha(study.HERE / "SAMPLE_v1.json"),
        "v1_extractor_sha256": sha(study.HERE / "study.py"),
        "v11_study_method_sha256": sha(METHOD),
        "v11_adapter_sha256": sha(Path(__file__)),
        "persona_report_sha256": {
            row["persona_id"]: _canonical_hash(row)
            for row in sorted(reports, key=lambda item: item["persona_id"])
        },
        "n_reports": 15,
        "n_claims": 245,
        "n_score_assessments": 45,
    }
    if len(source["persona_report_sha256"]) != 15:
        raise ValueError("Duplicate recovered persona report ID")
    return inventory, source


def _checked_inventory(out_dir: Path) -> dict:
    inventory, source = validated_inventory()
    saved = study.read_json(out_dir / "source.lock.json")
    expected = {**source, "inventory_sha256": sha(out_dir / "inventory.json")}
    if saved != expected or study.read_json(out_dir / "inventory.json") != inventory:
        raise ValueError("Prepared study differs from source lock or recovered reports")
    return _blind_inventory(inventory)


def prepare(out_dir: Path = STUDY_DIR) -> dict:
    inventory, source = validated_inventory()
    if out_dir.exists():
        raise FileExistsError("Study directory already exists")
    if out_dir.resolve().is_relative_to((study.EVALS / "results").resolve()):
        raise ValueError("Study output must remain separate from evaluation results")
    out_dir.mkdir(parents=True)
    study.write_json(out_dir / "inventory.json", inventory)
    source["inventory_sha256"] = sha(out_dir / "inventory.json")
    study.write_json(out_dir / "source.lock.json", source)
    rows = [{field: item.get(field, "") for field in study.CLAIM_FIELDS}
            for item in _blind_inventory(inventory)["claims"]]
    study.write_csv(out_dir / "claims_initial_blind.csv", study.CLAIM_FIELDS, rows)
    return {"reports": 15, "claims": len(rows), "score_assessments": 45,
            "claim_sheet": str(out_dir / "claims_initial_blind.csv")}


def verify(out_dir: Path = STUDY_DIR) -> dict:
    inventory = _checked_inventory(out_dir)
    rows = study.read_csv(out_dir / "claims_initial_blind.csv", study.CLAIM_FIELDS)
    study._unchanged_context(rows, inventory["claims"], "claim_id", {"verdict", "note"})
    if [row["claim_id"] for row in rows] != [item["claim_id"] for item in inventory["claims"]]:
        raise ValueError("Blind claim order changed")
    if len(rows) != 245:
        raise ValueError("Claim sheet must contain 245 unique claims")
    return {"reports": 15, "claims": len(rows), "score_assessments": 45,
            "human_verdicts_entered": sum(bool(row["verdict"].strip()) for row in rows),
            "score_sheet_released": (out_dir / "scores_initial.csv").exists()}


def freeze_claims(out_dir: Path = STUDY_DIR) -> None:
    inventory = _checked_inventory(out_dir)
    verify(out_dir)
    study._claim_rows(out_dir, inventory)
    lock = out_dir / "claims_initial.lock.json"
    if lock.exists() or (out_dir / "scores_initial.csv").exists():
        raise FileExistsError("Initial claims already frozen or score sheet released")
    study.write_json(lock, {"claims_initial_sha256": sha(out_dir / "claims_initial_blind.csv"),
                            "source_lock_sha256": sha(out_dir / "source.lock.json")})
    rows = [{field: item.get(field, "") for field in study.SCORE_FIELDS}
            for item in inventory["scores"]]
    study.write_csv(out_dir / "scores_initial.csv", study.SCORE_FIELDS, rows)


def freeze_initial(out_dir: Path = STUDY_DIR) -> None:
    inventory = _checked_inventory(out_dir)
    lock = study.read_json(out_dir / "claims_initial.lock.json")
    if lock.get("source_lock_sha256") != sha(out_dir / "source.lock.json"):
        raise ValueError("Claim lock source changed")
    study._initial_rows(out_dir, inventory)
    path = out_dir / "initial.lock.json"
    if path.exists():
        raise FileExistsError("Initial human review already frozen")
    study.write_json(path, {name: sha(out_dir / name) for name in (
        "source.lock.json", "claims_initial.lock.json", "claims_initial_blind.csv",
        "scores_initial.csv",
    )})
    study.write_csv(out_dir / "claims_ai.csv",
                    ("claim_id", "assistant", "suggested_verdict", "rationale"), [])
    study.write_csv(out_dir / "scores_ai.csv",
                    ("score_review_id", "assistant", "suggested_verdict", "rationale"), [])
    study.write_csv(out_dir / "claims_final.csv",
                    ("claim_id", "final_verdict", "ai_considered", "change_reason"),
                    [{"claim_id": x["claim_id"], "final_verdict": "", "ai_considered": "",
                      "change_reason": ""} for x in inventory["claims"]])
    study.write_csv(out_dir / "scores_final.csv",
                    ("score_review_id", "final_verdict", "material_omission",
                     "omission_detail", "ai_considered", "change_reason"),
                    [{"score_review_id": x["score_review_id"], "final_verdict": "",
                      "material_omission": "", "omission_detail": "", "ai_considered": "",
                      "change_reason": ""} for x in inventory["scores"]])


def freeze_final(out_dir: Path = STUDY_DIR) -> None:
    inventory = _checked_inventory(out_dir)
    study._final_rows(out_dir, inventory)
    path = out_dir / "final.lock.json"
    if path.exists():
        raise FileExistsError("Final human adjudication already frozen")
    study.write_json(path, {name: sha(out_dir / name) for name in (
        "initial.lock.json", "claims_ai.csv", "scores_ai.csv", "claims_final.csv",
        "scores_final.csv",
    )})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify", "freeze-claims",
                                            "freeze-initial", "freeze-final"))
    parser.add_argument("study_dir", nargs="?", type=Path, default=STUDY_DIR)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.study_dir)
    elif args.command == "verify":
        result = verify(args.study_dir)
    else:
        {"freeze-claims": freeze_claims, "freeze-initial": freeze_initial,
         "freeze-final": freeze_final}[args.command](args.study_dir)
        result = {"stage": args.command, "status": "frozen"}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
