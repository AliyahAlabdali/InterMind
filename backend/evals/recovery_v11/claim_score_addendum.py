"""Offline, write-once release of v1.1a score-band defensibility packets.

From backend/: python -m evals.recovery_v11.claim_score_addendum release
This module never calls an API, changes source reports, or fills human judgments.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from evals.claim_validity import study
from evals.datasets.evaluation.personas import PERSONAS
from evals.recovery_v11 import claim_study
from evals.recovery_v11.audit import OUTPUT, SOURCE, sha
from evals.recovery_v11.followup_discrimination import RESULTS

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
VERSION = "1.1a"
ADDENDUM = HERE / "CLAIM_SCORE_VALIDITY_ADDENDUM_v1.1a.md"
ADOPTED = HERE / "human_review" / "intermind_final_user_adjudicated_245.csv"
OUT = OUTPUT / "claim_score_addendum_v1.1a"
SHEET = "scores_band_review_v1.1a.csv"
CLAIM_SOURCE = claim_study.STUDY_DIR

# Earlier handoff hashes bind the inputs that are outside the frozen protocol locks.
BASELINE_SHA256 = {
    "inventory.json": "1c106ab2c9c3ed61527ec30b560590ddf22fa95e975f54b5f0117b97d77cb2f3",
    "source.lock.json": "05b97d56a090d2fb90f02b2b71a1fa3e56cecfce8242739296e3b294c4055c63",
    "claims_initial_blind.csv":
        "392244d1419bee73751f8b034adac6204f0e61b5cc5c4a63eb73d7d38a93370d",
    "intermind_final_user_adjudicated_245.csv":
        "92968f5b181ef619962c9ef8549c15257ee7714b2469c2bbce60f431e1d6a55f",
}
SCORE_FIELDS = ("score_review_id", "report_id", "job_id", "category",
                *study.SCORE_FIELDS[1:])
JUDGMENT_FIELDS = ("verdict", "note", "material_omission", "omission_detail")
REVIEW_REQUIRED = ("claim_id", "claim_text", "full_candidate_answer",
                   "final_human_verdict")


def _relative(path: Path) -> str:
    return path.resolve().relative_to(REPO.resolve()).as_posix()


def _input_paths() -> list[Path]:
    return [
        study.HERE / "PROTOCOL_v1.md",
        study.HERE / "RUBRIC_v1.md",
        study.HERE / "SAMPLE_v1.json",
        study.HERE / "STUDY.lock.json",
        study.HERE / "study.py",
        HERE / "CLAIM_STUDY_v1.1.md",
        HERE / "PROTOCOL_v1.1.lock.json",
        HERE / "claim_study.py",
        OUTPUT / "RECOVERY_MANIFEST_v1.1.json",
        RESULTS / "RESULT.lock.json",
        SOURCE / "progress.jsonl",
        SOURCE / "run_state.json",
        CLAIM_SOURCE / "inventory.json",
        CLAIM_SOURCE / "source.lock.json",
        CLAIM_SOURCE / "claims_initial_blind.csv",
        ADOPTED,
        ADDENDUM,
        Path(__file__),
    ]


def validate_adopted(rows: list[dict], claims: list[dict]) -> None:
    if len(rows) != 245 or len(claims) != 245:
        raise ValueError("Expected exactly 245 adopted judgments and frozen claims")
    source = {claim["claim_id"]: claim for claim in claims}
    ids = [row["claim_id"] for row in rows]
    if len(source) != 245 or len(set(ids)) != 245 or set(ids) != set(source):
        raise ValueError("Missing, duplicate, or unknown adopted claim IDs")
    for row in rows:
        if row["final_human_verdict"] not in study.CLAIM_VERDICTS:
            raise ValueError("Missing or invalid final human claim verdict")
        claim = source[row["claim_id"]]
        if (row["claim_text"] != claim["claim_text"]
                or row["full_candidate_answer"] != claim["full_candidate_answer"]):
            raise ValueError("Adjudicated claim text or candidate answer changed")


def validate_scores(scores: list[dict]) -> dict[str, str]:
    sample = study.read_json(study.HERE / "SAMPLE_v1.json")
    selected = study.selected_targets()
    target_category = {(item["job_id"], item["target"]): item["category"]
                       for item in sample["targets"]}
    if len(target_category) != 15 or any(len(targets) != 3 for targets in selected.values()):
        raise ValueError("Frozen score target selection changed")
    expected = {
        study._id("sc-", persona.persona_id, item["category"], item["target"]): (
            persona.persona_id, persona.jd_id, item["category"], item["target"]
        )
        for persona in PERSONAS for item in sample["targets"]
        if item["job_id"] == persona.jd_id
    }
    ids = [item["score_review_id"] for item in scores]
    if (len(scores) != 45 or len(expected) != 45 or len(set(ids)) != 45
            or set(ids) != set(expected)):
        raise ValueError("Score assessments differ from 45 frozen preselected IDs")
    per_report = Counter(item["report_id"] for item in scores)
    if len(per_report) != 15 or any(count != 3 for count in per_report.values()):
        raise ValueError("Every frozen report must have three score assessments")
    for item in scores:
        report_id, job_id, category, target = expected[item["score_review_id"]]
        if ((item["report_id"], item["job_id"], item["target"])
                != (report_id, job_id, target)
                or target_category.get((job_id, target)) != category
                or item["band"] != study.band(float(item["score"]))):
            raise ValueError("Score assessment source identity or band changed")
        for name in ("evidence_strings", "strengths", "weaknesses"):
            if not isinstance(json.loads(item[name]), list):
                raise ValueError(f"Score source field is not a list: {name}")
    return {item["score_review_id"]: expected[item["score_review_id"]][2]
            for item in scores}


def preflight() -> tuple[dict, list[dict], dict[str, str]]:
    """Finish all source and methodological checks before any release write."""
    inventory, source = claim_study.validated_inventory()
    for name, digest in BASELINE_SHA256.items():
        path = ADOPTED if name == ADOPTED.name else CLAIM_SOURCE / name
        if sha(path) != digest:
            raise ValueError(f"Source handoff hash changed: {name}")
    saved_lock = study.read_json(CLAIM_SOURCE / "source.lock.json")
    if (saved_lock != {**source, "inventory_sha256": sha(CLAIM_SOURCE / "inventory.json")}
            or study.read_json(CLAIM_SOURCE / "inventory.json") != inventory):
        raise ValueError("Source-locked inventory changed")
    if ((CLAIM_SOURCE / "claims_initial.lock.json").exists()
            or (CLAIM_SOURCE / "scores_initial.csv").exists()):
        raise ValueError("Original claim workflow has unexpectedly advanced")
    original_claims = study.read_csv(CLAIM_SOURCE / "claims_initial_blind.csv",
                                     study.CLAIM_FIELDS)
    if any(row["verdict"] or row["note"] for row in original_claims):
        raise ValueError("Original initial claim sheet is not blank")
    with ADOPTED.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not set(REVIEW_REQUIRED).issubset(reader.fieldnames or []):
            raise ValueError("Adopted review has missing required columns")
        adopted = list(reader)
    validate_adopted(adopted, inventory["claims"])
    categories = validate_scores(inventory["scores"])
    return inventory, adopted, categories


def _write_json_once(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def release(out_dir: Path = OUT) -> dict:
    if out_dir.exists():
        raise FileExistsError("v1.1a release directory already exists; refusing overwrite")
    inventory, adopted, categories = preflight()
    paths = _input_paths()
    if len({_relative(path) for path in paths}) != len(paths):
        raise ValueError("Duplicate provenance source path")
    inputs = {_relative(path): sha(path) for path in paths}
    score_rows = []
    for item in inventory["scores"]:
        row = {field: item.get(field, "") for field in SCORE_FIELDS}
        row["category"] = categories[item["score_review_id"]]
        score_rows.append(row)
    if any(any(row[field] for field in JUDGMENT_FIELDS) for row in score_rows):
        raise ValueError("Score review judgments must start blank")
    out_dir.mkdir(parents=True, exist_ok=False)
    sheet = out_dir / SHEET
    with sheet.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SCORE_FIELDS)
        writer.writeheader()
        writer.writerows(score_rows)
    manifest = {
        "version": VERSION,
        "status": "score_sheet_released_human_review_pending",
        "source_run_status": "incomplete",
        "method": "retrospective_deviation_from_frozen_claim_review_sequence",
        "adopted_claim_provenance": "one human adopted AI-assisted final adjudications",
        "operator_reported_sequence": [
            "source-locked claim extraction",
            "AI-assisted claim review",
            "disagreement re-evaluation",
            "human adoption of final 245 verdicts",
            "score assessments released under v1.1a only after source validation",
        ],
        "not_documented": [
            "independent pre-AI human initial claim review",
            "original initial-claim SHA-256 lock",
            "initial-to-final human verdict change history",
            "reviewer timestamps",
        ],
        "validation": {
            "adopted_claim_rows": len(adopted),
            "adopted_unique_valid_ids": 245,
            "adopted_exact_claim_text_and_answer_matches": 245,
            "source_reports": 15,
            "score_rows": len(score_rows),
            "unique_preselected_score_ids": len(categories),
            "scores_per_report": 3,
            "human_score_verdicts_entered": 0,
        },
        "input_sha256": inputs,
        "score_sheet_path": _relative(sheet),
        "score_sheet_sha256_at_release": sha(sheet),
        "score_sheet_fields": list(SCORE_FIELDS),
        "score_review_lock_created": False,
        "claim_metrics_calculated": False,
        "score_metrics_calculated": False,
    }
    manifest_path = out_dir / "PROVENANCE_MANIFEST.json"
    _write_json_once(manifest_path, manifest)
    _write_json_once(out_dir / "RELEASE.lock.json", {
        "version": VERSION,
        "status": "released_pending_human_review",
        "sha256": {
            _relative(manifest_path): sha(manifest_path),
            _relative(sheet): sha(sheet),
            _relative(ADDENDUM): sha(ADDENDUM),
            _relative(Path(__file__)): sha(Path(__file__)),
            _relative(ADOPTED): sha(ADOPTED),
        },
    })
    return {"score_rows": len(score_rows), "claim_rows_validated": len(adopted),
            "output_dir": str(out_dir), "score_sheet": str(sheet)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("release", "preflight"))
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()
    if args.command == "preflight":
        inventory, adopted, categories = preflight()
        result = {"claim_rows_validated": len(adopted), "score_rows_validated":
                  len(inventory["scores"]), "unique_score_ids": len(categories)}
    else:
        result = release(args.output_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
