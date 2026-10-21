"""v1.1 targeted answer-endpoint latency runner. Paid phases require explicit opt-in."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.agents.interview_graph import build_graph_state
from app.domain.candidate import Candidate
from app.repositories.ports import InterviewSession, StoredJob
from evals.datasets.evaluation.personas import JOBS
from evals.recovery_v11.ledger import PRICING, AttemptLedger, LedgerClient
from evals.run_interview_eval import _latency_app, _plan

HERE = Path(__file__).resolve().parent
LOCK = HERE / "PROTOCOL_v1.1.lock.json"
MAX_REQUESTS = 120
MAX_CALLS = 300
TARGET_PER_JOB = 20
WARMUPS = 3


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_lock() -> dict:
    from evals.claim_validity.study import require_study_lock
    from evals.run_interview_eval import _require_frozen_labels, _require_frozen_protocol

    _require_frozen_protocol()
    _require_frozen_labels()
    require_study_lock()
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    if lock.get("version") != "1.1" or lock.get("status") != "frozen":
        raise ValueError("Recovery protocol is not frozen")
    for relative, digest in lock["sha256"].items():
        if sha(HERE.parent / relative) != digest:
            raise ValueError(f"Recovery protocol input changed: {relative}")
    return lock


def require_successful_preflight(*, region: str, model: str) -> Path:
    """Paid latency cannot begin without a separate matching ten-request feasibility run."""
    root = HERE.parent / "results"
    for candidate in sorted(root.glob("*-v11-preflight"), reverse=True):
        try:
            state = json.loads((candidate / "run_state.json").read_text())
            events = [json.loads(line) for line in
                      (candidate / "requests.jsonl").read_text().splitlines()]
            results = [event for event in events if event.get("event") == "result"]
            starts = [event for event in events if event.get("event") == "started"]
            if (state.get("status") != "complete" or state.get("region") != region
                    or state.get("model") != model
                    or state.get("protocol_sha256") != sha(HERE / "PROTOCOL_v1.1.md")
                    or len(results) != 10 or len(starts) != 10
                    or {item["attempt_index"] for item in results} != set(range(10))
                    or {item["attempt_index"] for item in starts} != set(range(10))
                    or {item.get("job_id") for item in results}
                    != {job.jd_id for job in JOBS}
                    or any(sum(item.get("job_id") == job.jd_id for item in results) != 2
                           for job in JOBS)
                    or not all(usable(item) for item in results)):
                continue
            uri = f"file:{(candidate / 'api_ledger.sqlite').as_posix()}?mode=ro"
            with sqlite3.connect(uri, uri=True) as db:
                attempted, incomplete = db.execute(
                    "SELECT COUNT(*), SUM(status!='completed' OR estimated_usd IS NULL "
                    "OR returned_model IS NULL) FROM attempts"
                ).fetchone()
            if 0 < attempted <= 30 and not incomplete:
                return candidate
        except (OSError, ValueError, KeyError, sqlite3.Error):
            continue
    raise ValueError("Matching completed ten-request feasibility run required")


async def fixture(app, service, job, index: int):
    """Create an answerable graph checkpoint at a synthetic prior follow-up interrupt."""
    plan = await app.state.interview_plan_repository.get(job.jd_id)
    root = plan.coverage_targets[0]
    main_question = job.cases[0][2]
    followup_question = f"Give the concrete steps and validation for {root.target}."
    state = build_graph_state(plan)
    state.update({
        "status": "in_progress", "current_question_id": root.id,
        "current_question_text": followup_question,
        "asked_question_ids": [root.id], "follow_up_count": 0,
        "evaluation": "follow_up", "follow_up_question": followup_question,
        "history": [{
            "question_id": root.id, "root_question_id": root.id,
            "question": main_question, "answer": job.cases[0][5],
            "evaluation": None,
        }],
    })
    candidate = Candidate(name=f"Latency fixture {index}", email="")
    session = InterviewSession(job_id=job.jd_id, candidate_id=candidate.id)
    config = {"configurable": {"thread_id": session.id}}
    await service.graph.aupdate_state(config, state, as_node="evaluate_answer")
    await service.graph.ainvoke(None, config=config)
    try:
        session.runtime_snapshot = await service._snapshot(session.id)
    finally:
        await service.graph.checkpointer.adelete_thread(session.id)
    await app.state.candidate_repository.add(candidate)
    await app.state.interview_session_repository.add(session)
    answerable = service._saved_state(session)
    return session, answerable, job.cases[0][3]


def path_of(body: dict, previous_question_id: str) -> str:
    if body["current_question_is_follow_up"]:
        return "follow_up"
    if body["current_question_id"] not in (None, previous_question_id):
        return "advance"
    return "finish"


def usable(row: dict) -> bool:
    return (row["path"] == "advance" and row["http_status"] == 200
            and not row["warmup"] and not row["retried"])


def remaining_feasible(counts: dict[str, int], attempted: int,
                       limit: int = MAX_REQUESTS) -> bool:
    return sum(TARGET_PER_JOB - value for value in counts.values()) <= limit - attempted


async def collect(client, *, phase: str, on_row, on_start=None) -> list[dict]:
    """Run only when caller has completed paid guards; tests inject a fake client."""
    if phase not in {"preflight", "latency"}:
        raise ValueError("Unknown phase")
    app, service = _latency_app(client)
    jobs = sorted(JOBS, key=lambda job: job.jd_id)
    for job in jobs:
        await app.state.job_repository.add(StoredJob(
            id=job.jd_id, recruiter_id="evaluation-recruiter",
            job_description=job.text, job_spec={"role_title": job.role_title},
        ))
        await app.state.interview_plan_repository.add(_plan(job))
    limit = 10 if phase == "preflight" else MAX_REQUESTS
    rows: list[dict] = []
    counts = {job.jd_id: 0 for job in jobs}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://eval.local"
    ) as http:
        for index in range(limit):
            if phase == "latency" and all(n == TARGET_PER_JOB for n in counts.values()):
                break
            if hasattr(client, "ledger"):
                ledger = client.ledger
                attempted = ledger.summary()["attempted"]
                if attempted >= ledger.max_calls:
                    raise RuntimeError("Evaluation API call cap reached before sample target")
                if phase == "latency":
                    deficit = sum(TARGET_PER_JOB - value for value in counts.values())
                    if ledger.max_calls - attempted < 2 * deficit:
                        raise RuntimeError("API call budget cannot support remaining samples")
            warmup = phase == "latency" and index < WARMUPS
            if phase == "preflight":
                job = jobs[index % len(jobs)]
            elif warmup:
                job = jobs[index]
            else:
                needed = [job for job in jobs if counts[job.jd_id] < TARGET_PER_JOB]
                job = needed[(index - WARMUPS) % len(needed)]
            session, state, answer = await fixture(app, service, job, index)
            if hasattr(client, "endpoint_attempt"):
                client.endpoint_attempt = index
            events = client._trace.events
            event_start = len(events)
            if on_start is not None:
                on_start({"attempt_index": index, "job_id": job.jd_id,
                          "warmup": warmup, "status": "started"})
            started = time.perf_counter()
            status = None
            path = "error"
            error = None
            try:
                response = await http.post(
                    f"/interviews/{session.id}/answers",
                    json={"turn_id": state.current_turn_id, "answer": answer},
                    headers={"Authorization": f"Bearer {session.access_token}"},
                )
                status = response.status_code
                if status == 200:
                    path = path_of(response.json(), state.current_question_id)
                else:
                    error = f"HTTP_{status}"
            except Exception as exc:
                error = type(exc).__name__
            elapsed = time.perf_counter() - started
            request_events = events[event_start:]
            question_calls = sum(
                event.operation == "generate_structured"
                and event.details.get("schema") == "GeneratedQuestionSet"
                for event in request_events
            )
            row = {
                "attempt_index": index, "job_id": job.jd_id,
                "seconds": elapsed, "path": path, "http_status": status,
                "warmup": warmup, "retried": question_calls > 1,
                "api_calls_in_request": sum(event.operation == "generate_structured"
                                            for event in request_events),
                "error_type": error,
            }
            rows.append(row)
            on_row(row)
            if hasattr(client, "endpoint_attempt"):
                client.endpoint_attempt = None
            if phase == "preflight":
                if not usable(row):
                    raise RuntimeError("Paid feasibility check failed; no latency run permitted")
            elif usable(row):
                counts[job.jd_id] += 1
            if phase == "latency":
                if not remaining_feasible(counts, len(rows), limit):
                    raise RuntimeError("100 balanced usable samples mathematically unreachable")
    if phase == "latency" and any(value != TARGET_PER_JOB for value in counts.values()):
        raise RuntimeError("Latency sample incomplete")
    return rows


async def run_paid(phase: str, *, allow_paid: bool) -> Path:
    if not allow_paid:
        raise ValueError("Explicit --allow-paid required")
    require_lock()
    from app.core.config import get_settings

    settings = get_settings()
    region = os.environ.get("INTERMIND_EVAL_REGION", "").strip()
    if not region:
        raise ValueError("Actual executing client region required")
    if settings.llm_provider != "openai" or not settings.openai_api_key:
        raise ValueError("OpenAI provider and credentials required")
    if settings.openai_model != PRICING["model"]:
        raise ValueError("Model and pricing mismatch")
    if phase not in {"preflight", "latency"}:
        raise ValueError("Unknown phase")
    if phase == "latency":
        require_successful_preflight(region=region, model=settings.openai_model)
    root = HERE.parent / "results"
    name = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-v11-{phase}"
    out = root / name
    out.mkdir(exist_ok=False)
    ledger = AttemptLedger(
        out / "api_ledger.sqlite", max_calls=30 if phase == "preflight" else MAX_CALLS
    )
    client = LedgerClient(ledger=ledger, api_key=settings.openai_api_key,
                          model=settings.openai_model)
    (out / "run_state.json").write_text(json.dumps({"status": "incomplete",
        "protocol_sha256": sha(HERE / "PROTOCOL_v1.1.md"), "region": region,
        "model": settings.openai_model}) + "\n")

    def append(event: dict) -> None:
        with (out / "requests.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(event) + "\n")
            file.flush()
            os.fsync(file.fileno())

    def save(row: dict) -> None:
        append({"event": "result", **row})

    def start(row: dict) -> None:
        append({"event": "started", **row})

    try:
        rows = await collect(client, phase=phase, on_row=save, on_start=start)
        summary = ledger.summary()
        (out / "usage_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        (out / "run_state.json").write_text(json.dumps({"status": "complete",
            "protocol_sha256": sha(HERE / "PROTOCOL_v1.1.md"),
            "region": region, "model": settings.openai_model,
            "endpoint_attempts": len(rows)}) + "\n")
    except BaseException as exc:
        (out / "usage_summary.json").write_text(
            json.dumps(ledger.summary(), indent=2) + "\n"
        )
        (out / "run_state.json").write_text(json.dumps({
            "status": "interrupted" if not isinstance(exc, Exception) else "failed",
            "error_type": type(exc).__name__,
            "protocol_sha256": sha(HERE / "PROTOCOL_v1.1.md"), "region": region,
            "model": settings.openai_model,
        }) + "\n")
        raise
    finally:
        ledger.close()
    return out


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["preflight", "latency"])
    parser.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args()
    print(asyncio.run(run_paid(args.phase, allow_paid=args.allow_paid)))


if __name__ == "__main__":
    main()
