"""Offline guards for the four-metric harness; no API client is called."""

import csv
import json
from pathlib import Path

import pytest

import evals.run_interview_eval as cli
from app.domain.interview import InterviewState
from app.domain.report import InterviewReport, QuestionEvaluationSummary
from app.llm.fake_client import FakeLLMClient
from app.services.answer_evaluation import AnswerEvaluationService
from app.services.report_generation import ReportGenerationService
from app.services.report_narrative import ReportNarrativeService
from evals.datasets.development.grounding_cases import CASES as DEVELOPMENT_CASES
from evals.datasets.evaluation.followup_cases import CASES
from evals.datasets.evaluation.personas import JOBS, PERSONAS
from evals.datasets.pilot.cases import FOLLOWUPS
from evals.datasets.pilot.cases import JOBS as PILOT_JOBS
from evals.datasets.pilot.cases import PERSONAS as PILOT_PERSONAS
from evals.harness.evidence import blinded_adjudication, extract_evidence
from evals.harness.metrics import (
    discrimination_metrics,
    followup_metrics,
    latency_metrics,
    nearest_rank,
    token_cost,
    traceability_metrics,
    wilson,
)
from evals.run_interview_eval import (
    LABELS,
    _latency_run,
    _persona_run,
    _require_frozen_labels,
    _usable_advance_count,
    run,
)

pytestmark = pytest.mark.private_history


def test_dataset_size_uniqueness_and_separation():
    assert len(CASES) == 90
    assert len({case.case_id for case in CASES}) == 90
    assert len(JOBS) == 5 and len(PERSONAS) == 15
    assert all(len(persona.answers) == 10 for persona in PERSONAS)
    assert {c.case_id for c in CASES}.isdisjoint(c.case_id for c in FOLLOWUPS)
    assert {(c.target, c.question, c.answer) for c in CASES}.isdisjoint(
        (c.target, c.question, c.answer) for c in FOLLOWUPS
    )
    assert {p.persona_id for p in PERSONAS}.isdisjoint(p.persona_id for p in PILOT_PERSONAS)
    assert {a.answer for p in PERSONAS for a in p.answers}.isdisjoint(
        a.answer for p in PILOT_PERSONAS for a in p.answers
    )
    development_answers = {case.answer for case in DEVELOPMENT_CASES}
    assert development_answers.isdisjoint(c.answer for c in CASES)
    assert development_answers.isdisjoint(a.answer for p in PERSONAS for a in p.answers)
    for job in JOBS:
        cohorts = [p for p in PERSONAS if p.jd_id == job.jd_id]
        assert {p.tier for p in cohorts} == {"strong", "mixed", "weak"}
        assert len({tuple(a.target for a in p.answers) for p in cohorts}) == 1
        assert len({a.target for a in cohorts[0].answers}) == 10


def test_blind_label_file_has_90_human_labels_and_inputs_only():
    with Path(LABELS).open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 90
    assert {row["case_id"] for row in rows} == {case.case_id for case in CASES}
    assert all(row["label"] in {
        "FOLLOW_UP_WARRANTED", "NO_FOLLOW_UP_WARRANTED", "AMBIGUOUS"
    } for row in rows)
    assert set(rows[0]) == {
        "case_id", "target", "question", "answer", "prior_exchange", "label"
    }


def test_followup_confusion_f1_and_ambiguous_sensitivity():
    rows = [
        ("FOLLOW_UP_WARRANTED", "follow_up"),
        ("FOLLOW_UP_WARRANTED", "advance"),
        ("NO_FOLLOW_UP_WARRANTED", "follow_up"),
        ("NO_FOLLOW_UP_WARRANTED", "advance"),
        ("AMBIGUOUS", "follow_up"),
    ]
    result = followup_metrics(rows, cluster_ids=["q1", "q1", "q2", "q2", "q3"],
                              bootstrap_samples=100)
    assert (result["tp"], result["fp"], result["fn"], result["tn"]) == (1, 1, 1, 1)
    assert result["f1"] == .5 and result["n_primary"] == 4
    assert result["n_bootstrap_clusters"] == 2
    assert result["ambiguous"] == 1
    assert result["ambiguous_sensitivity_f1"]["all_warranted"] > .5
    with pytest.raises(ValueError, match="cluster ID"):
        followup_metrics(rows, cluster_ids=["q1"])


def test_traceability_needs_human_verdict_for_every_ambiguous_string():
    rows = [{"evidence_id": "a", "tier": "supported_exact"},
            {"evidence_id": "b", "tier": "ambiguous"},
            {"evidence_id": "c", "tier": "ambiguous"}]
    with pytest.raises(ValueError):
        traceability_metrics(rows, {"b": "supported"})
    result = traceability_metrics(rows, {"b": "supported", "c": "cannot_tell"})
    assert result["traceability"] == 2 / 3
    assert result["unsupported_rate"] == 1 / 3
    assert result["cannot_tell"] == 1


def test_evidence_uses_all_direct_answers_not_last_report_answer():
    report = InterviewReport(
        interview_id="interview", job_id="job", overall_score=.7,
        recommendation="consider", summary="Summary",
        question_evaluations=[QuestionEvaluationSummary(
            target_id="root", question_id="followup", question="And then?",
            category="technology", target="Kubernetes", candidate_answer="We verified it.",
            evidence=["I wrote the Helm charts myself"],
        )],
    )
    state = InterviewState(job_id="job", history=[
        {"question_id": "root", "root_question_id": "root", "answer":
         "I wrote the Helm charts myself when we moved payments to Kubernetes.",
         "evaluation": {"evidence": ["I wrote the Helm charts myself"]}},
        {"question_id": "followup", "root_question_id": "root", "answer": "We verified it.",
         "evaluation": {"evidence": []}},
    ])
    rows = extract_evidence(report, state)
    assert rows[0]["tier"] == "supported_exact"
    assert len(rows[0]["source_answers"]) == 2


def test_cross_target_source_is_candidate_answer_not_synthesized_note():
    report = InterviewReport(
        interview_id="interview", job_id="job", overall_score=.7,
        recommendation="consider", summary="Summary",
        question_evaluations=[QuestionEvaluationSummary(
            target_id="other", question_id="other", question="Not asked directly",
            category="technology", target="Python", candidate_answer="model note",
            evidence=["I wrote the Python parser for the feed"],
            assessment_method="cross_target",
        )],
    )
    state = InterviewState(job_id="job", history=[
        {"question_id": "root", "root_question_id": "root",
         "answer": "I wrote the Python parser for the feed and then deployed it.",
         "evaluation": {"evidence": []}},
        {"question_id": "other", "root_question_id": "other", "answer": "model note",
         "assessment_method": "cross_target",
         "evaluation": {"evidence": ["I wrote the Python parser for the feed"]}},
    ])
    rows = extract_evidence(report, state)
    assert rows[0]["tier"] == "supported_exact"
    assert rows[0]["source_answers"] == [state.history[0]["answer"]]
    blind = blinded_adjudication([{**rows[0], "tier": "ambiguous"}])[0]
    assert set(blind) == {"evidence_id", "evidence_string", "source_answers", "verdict"}


def test_discrimination_gate_and_sample_sizes():
    rows = [{"jd_id": str(i), "tier": tier, "score": score,
             "recommendation": "hire" if score > .5 else "no_hire"}
            for i in range(5)
            for tier, score in (("strong", .9), ("mixed", .55), ("weak", .2))]
    result = discrimination_metrics(rows)
    assert result["n_jobs"] == 5 and result["n_personas"] == 15
    assert result["ordered_jobs"] == 5 and result["gate_passed"]
    rows[0]["score"] = .1
    rows[3]["score"] = .1
    assert not discrimination_metrics(rows)["gate_passed"]


def test_latency_nearest_rank_excludes_followup_warmup_and_retry():
    rows = [{"seconds": float(i), "path": "advance", "warmup": False}
            for i in range(1, 21)]
    rows += [{"seconds": 500., "path": "follow_up"},
             {"seconds": 600., "path": "advance", "warmup": True},
             {"seconds": 700., "path": "advance", "retried": True}]
    result = latency_metrics(rows)
    assert result["n_advance"] == 20
    assert result["p95_seconds"] == 19.
    assert _usable_advance_count(rows) == 20
    assert nearest_rank([1, 2, 3], .95) == 3
    assert wilson(0, 10)[0] == 0


def test_cost_uses_sdk_usage_not_text_length():
    events = [{"operation": "generate_structured_completed", "prompt_tokens": 2000,
               "completion_tokens": 400, "cached_prompt_tokens": 1000},
              {"operation": "generate_structured_failed"}]
    assert token_cost(events, .15, .60, .075)["estimated_usd"] == pytest.approx(.000465)
    with pytest.raises(ValueError):
        token_cost([{"operation": "generate_structured_completed"}], .15, .60)


def test_model_metadata_separates_requested_alias_from_completed_response_id():
    events = [
        {"operation": "generate_structured", "model": "gpt-4o-mini"},
        {"operation": "generate_structured_completed",
         "model": "gpt-4o-mini-2024-07-18"},
        {"operation": "generate_structured_failed", "model": "unreturned-model"},
    ]
    assert cli._model_metadata(events) == {
        "models_requested": ["gpt-4o-mini"],
        "models_returned": ["gpt-4o-mini-2024-07-18"],
    }
    assert cli._model_metadata(events[:1])["models_returned"] == []


def test_final_requires_recorded_client_region(monkeypatch):
    monkeypatch.delenv("INTERMIND_EVAL_REGION", raising=False)
    assert cli._client_region("pilot") == "unspecified"
    with pytest.raises(ValueError, match="INTERMIND_EVAL_REGION"):
        cli._client_region("final")
    monkeypatch.setenv("INTERMIND_EVAL_REGION", "  Riyadh, Saudi Arabia  ")
    assert cli._client_region("final") == "Riyadh, Saudi Arabia"


async def test_paid_commands_require_explicit_flag_and_frozen_human_labels(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="explicit"):
        await run("pilot", allow_paid=False)
    monkeypatch.setattr(cli, "PROTOCOL_LOCK", tmp_path / "missing.protocol.json")
    with pytest.raises(ValueError, match="protocol is frozen"):
        await run("pilot", allow_paid=True)
    monkeypatch.setattr(cli, "LOCK", tmp_path / "missing.lock.json")
    with pytest.raises(ValueError, match="frozen"):
        await run("final", allow_paid=True)
    with pytest.raises(ValueError, match="frozen"):
        _require_frozen_labels()


def test_label_freeze_requires_complete_labels_and_detects_edits(tmp_path, monkeypatch):
    labels = tmp_path / "blind.csv"
    frozen = tmp_path / "blind.frozen.csv"
    lock = tmp_path / "labels.lock.json"
    monkeypatch.setattr(cli, "LABELS", labels)
    monkeypatch.setattr(cli, "FROZEN_LABELS", frozen)
    monkeypatch.setattr(cli, "LOCK", lock)
    rows = [{"case_id": case.case_id, "target": case.target,
             "question": case.question, "answer": case.answer,
             "prior_exchange": json.dumps(case.prior_exchange), "label": ""}
            for case in CASES]
    with labels.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="Every case"):
        cli.freeze_labels()
    rows[0]["label"] = "AMBIGUOUS"
    for row in rows[1:]:
        row["label"] = "NO_FOLLOW_UP_WARRANTED"
    with labels.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    cli.freeze_labels()
    assert len(cli._require_frozen_labels()) == 90
    assert frozen.read_bytes() == labels.read_bytes()
    assert json.loads(lock.read_text(encoding="utf-8"))["frozen_copy_sha256"] == cli._sha(frozen)
    with pytest.raises(FileExistsError, match="already frozen"):
        cli.freeze_labels()
    labels.write_text(labels.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        cli._require_frozen_labels()
    labels.write_bytes(frozen.read_bytes())
    frozen.chmod(0o666)
    frozen.write_text(frozen.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="copy changed"):
        cli._require_frozen_labels()


def test_protocol_lock_rejects_final_dataset_change(monkeypatch):
    lock = cli._require_frozen_protocol()
    assert lock["labels_sha256"] == cli._sha(cli.LABELS)
    snapshot = cli._protocol_snapshot()
    monkeypatch.setattr(cli, "_protocol_snapshot", lambda: {
        **snapshot, "datasets/evaluation/followup_cases.py": "changed"
    })
    with pytest.raises(ValueError, match="dataset"):
        cli._require_frozen_protocol()


def test_incomplete_run_cannot_be_aggregated(tmp_path):
    (tmp_path / "run_state.json").write_text('{"status":"incomplete"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Incomplete"):
        cli.aggregate(tmp_path)


async def test_pilot_fixed_turn_report_and_endpoint_latency_with_fake_client():
    fake = FakeLLMClient()
    scores, evidence = await _persona_run(
        PILOT_JOBS, PILOT_PERSONAS, AnswerEvaluationService(fake),
        ReportGenerationService(ReportNarrativeService(fake)),
    )
    assert len(scores) == 3
    assert all(len(score["report"]["question_evaluations"]) == 5 for score in scores)
    assert all(row["source_answers"] for row in evidence)
    rows = await _latency_run(fake, PILOT_JOBS[0], target_n=1, max_sessions=4)
    assert latency_metrics(rows)["n_advance"] == 1
