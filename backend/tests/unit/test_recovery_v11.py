"""Offline-only tests for the separately versioned recovery tooling."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain.interview_plan import GeneratedQuestionSet
from app.llm.fake_client import FakeLLMClient
from app.llm.openai_client import OpenAIStructuredClient
from app.observability.trace import TraceRecorder
from evals.recovery_v11 import audit, latency
from evals.recovery_v11.ledger import AttemptLedger, LedgerClient

pytestmark = pytest.mark.private_history


def test_recovery_audit_validates_exact_saved_outputs():
    manifest, review = audit.audit()
    assert manifest["source_status"] == "incomplete"
    assert manifest["validation"]["followups"] == 90
    assert manifest["validation"]["persona_reports"] == 15
    assert manifest["validation"]["question_assessments"] == 150
    assert manifest["validation"]["evidence_strings"] == 239
    assert manifest["validation"]["evidence_attribution"] == {
        "unique_target_exact": 217, "lexical_target_requires_review": 4,
        "unattributable_automatically": 18,
    }
    assert len(review) == 22
    assert all(not row["verdict"] and not row["source_answer_index"] for row in review)
    assert not manifest["eligible_v1_final_metrics"]


def test_write_once_manifest_does_not_touch_source(tmp_path, monkeypatch):
    original = audit.sha(audit.SOURCE / "progress.jsonl")
    monkeypatch.setattr(audit, "OUTPUT", tmp_path / "new")
    manifest = audit.write_once()
    path = audit.OUTPUT / "RECOVERY_MANIFEST_v1.1.json"
    assert json.loads(path.read_text(encoding="utf-8")) == manifest
    assert (audit.OUTPUT / "RECOVERY_MANIFEST_v1.1.sha256").read_text().strip() == audit.sha(path)
    assert audit.sha(audit.SOURCE / "progress.jsonl") == original
    with pytest.raises(FileExistsError):
        audit.write_once()


def test_ledger_unknown_failure_usage_and_cap(tmp_path: Path):
    ledger = AttemptLedger(tmp_path / "ledger.sqlite", max_calls=3)
    unknown = ledger.start("AnswerEvaluation", "gpt-4o-mini")
    done = ledger.start("GeneratedQuestionSet", "gpt-4o-mini")
    ledger.finish(done, returned_model="gpt-4o-mini-2024-07-18",
                  input_tokens=1000, output_tokens=100, cached_tokens=500)
    failed = ledger.start("GeneratedQuestionSet", "gpt-4o-mini")
    ledger.finish(failed, error_type="TimeoutError")
    with pytest.raises(RuntimeError, match="cap"):
        ledger.start("AnswerEvaluation", "gpt-4o-mini")
    with pytest.raises(ValueError, match="already reconciled"):
        ledger.finish(done, input_tokens=1, output_tokens=1)
    assert unknown != done != failed
    summary = ledger.summary()
    assert (summary["attempted"], summary["completed"], summary["failed"],
            summary["interrupted_or_unknown"]) == (3, 1, 1, 1)
    assert summary["input_tokens_known"] == 1000
    assert summary["cached_tokens_known"] == 500
    assert summary["known_estimated_usd"] > 0
    assert not summary["total_cost_complete"]
    ledger.close()
    reopened = AttemptLedger(tmp_path / "ledger.sqlite", max_calls=3)
    assert reopened.summary() == summary
    reopened.close()


def test_completed_call_without_provider_usage_keeps_cost_unknown(tmp_path: Path):
    ledger = AttemptLedger(tmp_path / "ledger.sqlite", max_calls=1)
    attempt = ledger.start("AnswerEvaluation", "gpt-4o-mini")
    ledger.finish(attempt, returned_model="gpt-4o-mini-2024-07-18")
    summary = ledger.summary()
    assert summary["completed"] == 1
    assert summary["known_estimated_usd"] == 0
    assert not summary["total_cost_complete"]
    ledger.close()


@pytest.mark.asyncio
async def test_ledger_client_distinguishes_requested_and_returned_model(tmp_path, monkeypatch):
    async def simulated_parse(**kwargs):
        return SimpleNamespace(
            model="gpt-4o-mini-2024-07-18",
            usage=SimpleNamespace(prompt_tokens=120, completion_tokens=20,
                                  prompt_tokens_details=SimpleNamespace(cached_tokens=40)),
            choices=[SimpleNamespace(message=SimpleNamespace(
                parsed=GeneratedQuestionSet(), refusal=None
            ))],
        )

    ledger = AttemptLedger(tmp_path / "ledger.sqlite", max_calls=1)
    client = LedgerClient(ledger=ledger, api_key="offline-test-key", model="gpt-4o-mini")
    monkeypatch.setattr(client, "_original_parse", simulated_parse)
    await client.generate_structured(prompt="x", input_text="y", schema=GeneratedQuestionSet)
    row = ledger.db.execute("SELECT requested_model,returned_model,status FROM attempts").fetchone()
    assert row == ("gpt-4o-mini", "gpt-4o-mini-2024-07-18", "completed")
    ledger.close()


@pytest.mark.asyncio
async def test_interrupted_call_stays_unknown(tmp_path, monkeypatch):
    async def interrupted(self, *, prompt, input_text, schema):
        raise KeyboardInterrupt()

    monkeypatch.setattr(OpenAIStructuredClient, "generate_structured", interrupted)
    ledger = AttemptLedger(tmp_path / "ledger.sqlite", max_calls=1)
    client = LedgerClient(ledger=ledger, api_key="offline-test-key", model="gpt-4o-mini")
    with pytest.raises(KeyboardInterrupt):
        await client.generate_structured(prompt="x", input_text="y",
                                         schema=GeneratedQuestionSet)
    assert ledger.summary()["interrupted_or_unknown"] == 1
    assert not ledger.summary()["total_cost_complete"]
    ledger.close()


@pytest.mark.asyncio
async def test_fixture_uses_real_endpoint_with_fake_llm():
    client = FakeLLMClient()
    client._trace = TraceRecorder()
    rows = await latency.collect(client, phase="preflight", on_row=lambda _: None)
    assert len(rows) == 10
    assert all(row["http_status"] == 200 and row["path"] == "advance" for row in rows)
    assert {row["job_id"] for row in rows} == {job.jd_id for job in latency.JOBS}


@pytest.mark.asyncio
async def test_latency_controller_meets_fixed_five_job_quota_offline():
    client = FakeLLMClient()
    client._trace = TraceRecorder()
    started = []
    rows = await latency.collect(
        client, phase="latency", on_row=lambda _: None, on_start=started.append
    )
    assert len(rows) == len(started) == 103
    assert sum(row["warmup"] for row in rows) == 3
    for job in latency.JOBS:
        assert sum(row["job_id"] == job.jd_id and latency.usable(row)
                   for row in rows) == 20


@pytest.mark.asyncio
async def test_application_retry_is_logged_and_blocks_feasibility():
    class RetryFake(FakeLLMClient):
        def __init__(self):
            super().__init__()
            self._trace = TraceRecorder()
            self.first_question = True

        async def generate_structured(self, *, prompt, input_text, schema):
            self._trace.record(operation="generate_structured", schema=schema.__name__)
            if schema is GeneratedQuestionSet and self.first_question:
                self.first_question = False
                return GeneratedQuestionSet(questions=[])
            return await super().generate_structured(
                prompt=prompt, input_text=input_text, schema=schema
            )

    rows = []
    with pytest.raises(RuntimeError, match="feasibility"):
        await latency.collect(RetryFake(), phase="preflight", on_row=rows.append)
    assert len(rows) == 1 and rows[0]["retried"]


def test_feasibility_stop_and_paid_guard():
    counts = {str(i): 20 for i in range(5)}
    counts["0"] = 10
    assert latency.remaining_feasible(counts, attempted=110)
    assert not latency.remaining_feasible(counts, attempted=111)
    with pytest.raises(ValueError, match="allow-paid"):
        asyncio.run(latency.run_paid("preflight", allow_paid=False))


def test_paid_latency_requires_matching_completed_preflight(tmp_path, monkeypatch):
    here = tmp_path / "recovery_v11"
    here.mkdir()
    (here / "PROTOCOL_v1.1.md").write_text("test protocol")
    monkeypatch.setattr(latency, "HERE", here)
    with pytest.raises(ValueError, match="feasibility"):
        latency.require_successful_preflight(region="Makkah", model="gpt-4o-mini")
    out = tmp_path / "results" / "test-v11-preflight"
    out.mkdir(parents=True)
    (out / "run_state.json").write_text(json.dumps({
        "status": "complete", "region": "Makkah", "model": "gpt-4o-mini",
        "protocol_sha256": latency.sha(here / "PROTOCOL_v1.1.md"),
    }))
    events = []
    jobs = sorted(latency.JOBS, key=lambda job: job.jd_id)
    for i in range(10):
        job_id = jobs[i % 5].jd_id
        events.append({"event": "started", "attempt_index": i, "job_id": job_id})
        events.append({"event": "result", "attempt_index": i,
                       "job_id": job_id,
                       "path": "advance", "http_status": 200,
                       "warmup": False, "retried": False})
    (out / "requests.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    ledger = AttemptLedger(out / "api_ledger.sqlite", max_calls=30)
    for _ in range(10):
        attempt = ledger.start("AnswerEvaluation", "gpt-4o-mini")
        ledger.finish(attempt, returned_model="gpt-4o-mini-2024-07-18",
                      input_tokens=10, output_tokens=2)
    ledger.close()
    assert latency.require_successful_preflight(
        region="Makkah", model="gpt-4o-mini"
    ) == out
    with pytest.raises(ValueError, match="feasibility"):
        latency.require_successful_preflight(region="Other", model="gpt-4o-mini")
