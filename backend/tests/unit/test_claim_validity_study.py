"""Offline tests for the separately frozen claim and score study."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from evals.claim_validity import study
from evals.datasets.evaluation.personas import JOBS, PERSONAS

pytestmark = pytest.mark.private_history


def fake_reports() -> list[dict]:
    by_job = {job.jd_id: job for job in JOBS}
    rows = []
    for persona in PERSONAS:
        job = by_job[persona.jd_id]
        score = {"strong": .8, "mixed": .5, "weak": .2}[persona.tier]
        questions = [
            {"category": case[0], "target": case[1], "question": answer.question,
             "candidate_answer": answer.answer, "score": score,
             "evidence": [], "strengths": ["Described a relevant action."],
             "weaknesses": ["The answer omitted a result."]}
            for case, answer in zip(job.cases, persona.answers, strict=True)
        ]
        _, recommendation = study.calculated_score_and_recommendation(questions)
        rows.append({"jd_id": job.jd_id, "persona_id": persona.persona_id,
                     "tier": persona.tier, "score": score, "recommendation": recommendation,
                     "report": {"interview_id": persona.persona_id,
                                "overall_score": score, "recommendation": recommendation,
                                "question_evaluations": questions,
                                "summary": (
                                    "The candidate described an approach. Results were limited."
                                ),
                                "strengths": ["Described a relevant action."],
                                "weaknesses": ["The answer omitted a result."]}})
    return rows


def write_csv_rows(path: Path, rows: list[dict], fields: tuple[str, ...]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)


def fill_initial(out_dir: Path) -> None:
    claims = study.read_csv(out_dir / "claims_initial_blind.csv", study.CLAIM_FIELDS)
    for row in claims:
        row["verdict"] = "SUPPORTED"
    write_csv_rows(out_dir / "claims_initial_blind.csv", claims, study.CLAIM_FIELDS)
    study.freeze_claims(out_dir)
    scores = study.read_csv(out_dir / "scores_initial.csv", study.SCORE_FIELDS)
    for row in scores:
        row["verdict"] = "DEFENSIBLE"
        row["material_omission"] = "NO"
    write_csv_rows(out_dir / "scores_initial.csv", scores, study.SCORE_FIELDS)


def test_fixed_sample_and_blind_extraction():
    sample = study.selected_targets()
    assert len(sample) == 5
    assert all(len(targets) == 3 for targets in sample.values())
    result = study.extract_inventory(fake_reports())
    assert len(result["scores"]) == 45
    assert len(result["calculation_checks"]) == 15
    assert len({item["claim_id"] for item in result["claims"]}) == len(result["claims"])
    assert "persona_tier" not in study.CLAIM_FIELDS
    assert "score" not in study.CLAIM_FIELDS
    assert "recommendation" not in study.CLAIM_FIELDS
    assert any(item["question"] == "Full interview" for item in result["claims"])


def test_pilot_and_incomplete_run_rejected(tmp_path):
    (tmp_path / "run_state.json").write_text('{"status":"complete"}', encoding="utf-8")
    (tmp_path / "metadata.json").write_text('{"pool":"pilot"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Only a complete final"):
        study._require_final_run(tmp_path)
    (tmp_path / "run_state.json").write_text('{"status":"incomplete"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Only a complete final"):
        study._require_final_run(tmp_path)


def test_arithmetic_or_source_mismatch_rejected():
    rows = fake_reports()
    rows[0]["report"]["overall_score"] = .99
    with pytest.raises(ValueError, match="arithmetic mismatch"):
        study.extract_inventory(rows)
    rows = fake_reports()
    rows[0]["report"]["question_evaluations"][0]["candidate_answer"] = "changed"
    with pytest.raises(ValueError, match="frozen source"):
        study.extract_inventory(rows)


def test_missing_duplicate_and_invalid_initial_claims(tmp_path):
    inventory = study.extract_inventory(fake_reports())
    rows = [{field: item.get(field, "") for field in study.CLAIM_FIELDS}
            for item in inventory["claims"]]
    write_csv_rows(tmp_path / "claims_initial_blind.csv", rows, study.CLAIM_FIELDS)
    with pytest.raises(ValueError, match="initial claim verdict"):
        study._claim_rows(tmp_path, inventory)
    for row in rows:
        row["verdict"] = "SUPPORTED"
    rows[0]["verdict"] = "MAYBE"
    write_csv_rows(tmp_path / "claims_initial_blind.csv", rows, study.CLAIM_FIELDS)
    with pytest.raises(ValueError, match="initial claim verdict"):
        study._claim_rows(tmp_path, inventory)
    rows[0]["verdict"] = "SUPPORTED"
    rows[1]["claim_id"] = rows[0]["claim_id"]
    write_csv_rows(tmp_path / "claims_initial_blind.csv", rows, study.CLAIM_FIELDS)
    with pytest.raises(ValueError, match="duplicate"):
        study._claim_rows(tmp_path, inventory)


def test_staged_locks_and_aggregation(tmp_path, monkeypatch):
    rows = fake_reports()
    result_dir = tmp_path / "final-result"
    result_dir.mkdir()
    (result_dir / "run_state.json").write_text('{"status":"complete"}', encoding="utf-8")
    v1 = study.read_json(study.EVALS / "PROTOCOL.lock.json")
    metadata = {"pool": "final", "model_configured": "gpt-4o-mini",
                "protocol_sha256": v1["files_sha256"]["PROTOCOL.md"],
                "labels_sha256": v1["labels_sha256"],
                "dataset_sha256": {"personas": v1["files_sha256"][
                    "datasets/evaluation/personas.py"]}}
    (result_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (result_dir / "persona_reports.json").write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setattr(study, "require_study_lock", lambda: {})
    # The study lock itself is present and checked by hash; only its internal verification
    # is bypassed here so the test can exercise temporary final-run files.
    out_dir = tmp_path / "study"
    result = study.prepare(result_dir, out_dir)
    assert result["n_target_assessments"] == 45
    assert not (out_dir / "scores_initial.csv").exists()
    fill_initial(out_dir)
    assert (out_dir / "scores_initial.csv").exists()
    study.freeze_initial(out_dir)
    with pytest.raises(ValueError, match="Missing or invalid final claim verdict"):
        study.freeze_final(out_dir)
    claims = study.read_csv(out_dir / "claims_final.csv",
                            ("claim_id", "final_verdict", "ai_considered", "change_reason"))
    for row in claims:
        row["final_verdict"] = "SUPPORTED"
        row["ai_considered"] = "NO"
    claims[0]["final_verdict"] = "UNSUPPORTED"
    claims[0]["ai_considered"] = "YES"
    write_csv_rows(out_dir / "claims_final.csv", claims,
                   ("claim_id", "final_verdict", "ai_considered", "change_reason"))
    scores = study.read_csv(out_dir / "scores_final.csv",
                            ("score_review_id", "final_verdict", "material_omission",
                             "omission_detail", "ai_considered", "change_reason"))
    for row in scores:
        row["final_verdict"] = "DEFENSIBLE"
        row["material_omission"] = "NO"
        row["ai_considered"] = "NO"
    write_csv_rows(out_dir / "scores_final.csv", scores,
                   ("score_review_id", "final_verdict", "material_omission",
                    "omission_detail", "ai_considered", "change_reason"))
    with pytest.raises(ValueError, match="AI assistance marked"):
        study.freeze_final(out_dir)
    write_csv_rows(out_dir / "claims_ai.csv",
                   [{"claim_id": claims[0]["claim_id"], "assistant": "ChatGPT",
                     "suggested_verdict": "PARTIALLY_SUPPORTED", "rationale": "Check qualifier."}],
                   ("claim_id", "assistant", "suggested_verdict", "rationale"))
    with pytest.raises(ValueError, match="Changed claim verdict needs a reason"):
        study.freeze_final(out_dir)
    claims[0]["change_reason"] = "Human reconsidered the source context."
    write_csv_rows(out_dir / "claims_final.csv", claims,
                   ("claim_id", "final_verdict", "ai_considered", "change_reason"))
    study.freeze_final(out_dir)
    output = study.aggregate(out_dir)
    assert output["claims"]["n"] == result["n_claims"]
    assert output["claims"]["mean_report_fully_supported_rate"] < 1.0
    assert output["claims"]["changed_after_initial"] == 1
    assert output["claims"]["ai_assisted_items"] == 1
    assert output["score_bands"]["n"] == 45
    assert output["deterministic_calculation_checks"]["passed"] == 15
    with pytest.raises(FileExistsError, match="already exist"):
        study.aggregate(out_dir)
    # An edited initial human verdict invalidates all downstream work.
    with (out_dir / "claims_initial_blind.csv").open("a", encoding="utf-8") as handle:
        handle.write("\n")
    with pytest.raises(ValueError, match="Initial human review changed"):
        study.freeze_final(out_dir)
