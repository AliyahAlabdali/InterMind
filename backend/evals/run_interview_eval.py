"""Four-metric evaluation CLI. Only `pilot` and `final` can contact OpenAI.

From backend/: python -m evals.run_interview_eval <command> --help
No paid command runs without --allow-paid. Final additionally requires frozen, complete
human labels. The command never writes predictions to the blind labeling file.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import platform
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from evals.datasets.evaluation import followup_cases, personas
from evals.datasets.pilot import cases as pilot_cases
from evals.harness.evidence import blinded_adjudication, extract_evidence
from evals.harness.metrics import (
    discrimination_metrics,
    followup_metrics,
    latency_metrics,
    token_cost,
    traceability_metrics,
)

ROOT = Path(__file__).resolve().parent
PROTOCOL = ROOT / "PROTOCOL.md"
PROTOCOL_LOCK = ROOT / "PROTOCOL.lock.json"
LABELS = ROOT / "labels" / "followup_blind.csv"
FROZEN_LABELS = ROOT / "labels" / "followup_blind.frozen.csv"
LOCK = ROOT / "labels" / "followup_labels.lock.json"
PRICING = {"date": "2026-10-12", "model": "gpt-4o-mini",
           "input_per_million_usd": 0.15, "cached_input_per_million_usd": 0.075,
           "output_per_million_usd": 0.60,
           "source": "https://developers.openai.com/api/docs/models/gpt-4o-mini"}


def _budgeted_client_class():
    from app.llm.openai_client import OpenAIStructuredClient

    class BudgetedClient(OpenAIStructuredClient):
        def __init__(self, *, max_calls: int, **kwargs):
            super().__init__(**kwargs)
            self.max_calls = max_calls
            self.calls_attempted = 0

        async def generate_structured(self, *, prompt, input_text, schema):
            if self.calls_attempted >= self.max_calls:
                raise RuntimeError("Evaluation API call cap reached; partial run retained")
            self.calls_attempted += 1
            return await super().generate_structured(
                prompt=prompt, input_text=input_text, schema=schema
            )

    return BudgetedClient


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def export_labels() -> None:
    if LABELS.exists():
        raise FileExistsError(f"Label file already exists; preserving human work: {LABELS}")
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"case_id": c.case_id, "target": c.target, "question": c.question,
             "answer": c.answer, "prior_exchange": json.dumps(c.prior_exchange), "label": ""}
            for c in followup_cases.CASES]
    _csv(LABELS, list(rows[0]), rows)
    print(f"Created {len(rows)} blind cases at {LABELS}")


def _validated_labels() -> dict[str, str]:
    expected = {c.case_id: c for c in followup_cases.CASES}
    rows = _read_csv(LABELS)
    ids = [row.get("case_id") for row in rows]
    valid = {"FOLLOW_UP_WARRANTED", "NO_FOLLOW_UP_WARRANTED", "AMBIGUOUS"}
    if len(ids) != 90 or set(ids) != set(expected) or len(set(ids)) != len(ids):
        raise ValueError("Label file must contain exactly the 90 final case IDs, once each")
    if any(set(row) != {"case_id", "target", "question", "answer", "prior_exchange", "label"}
           for row in rows):
        raise ValueError("The blind file columns changed")
    for row in rows:
        case = expected[row["case_id"]]
        try:
            prior = json.loads(row["prior_exchange"])
        except json.JSONDecodeError as exc:
            raise ValueError("A prior-exchange input was changed") from exc
        if ((row["target"], row["question"], row["answer"])
                != (case.target, case.question, case.answer)
                or prior != [list(pair) for pair in case.prior_exchange]):
            raise ValueError(f"Blind input changed for {row['case_id']}")
    if any(row.get("label", "").strip() not in valid for row in rows):
        raise ValueError("Every case needs one rubric label before labels can be frozen")
    return {row["case_id"]: row["label"].strip() for row in rows}


def freeze_labels() -> None:
    _validated_labels()
    if LOCK.exists() or FROZEN_LABELS.exists():
        raise FileExistsError("Labels are already frozen; do not overwrite the lock or copy")
    content = LABELS.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    with FROZEN_LABELS.open("xb") as output:
        output.write(content)
    os.chmod(FROZEN_LABELS, 0o444)
    with LOCK.open("x", encoding="utf-8") as output:
        json.dump({"labels_sha256": digest, "frozen_copy_sha256": digest,
                   "frozen_copy": FROZEN_LABELS.name,
                   "frozen_at_utc": datetime.now(UTC).isoformat(), "n": 90}, output,
                  indent=2)
        output.write("\n")
    print(f"Frozen 90 human labels at {FROZEN_LABELS} and {LOCK}")


def _require_frozen_labels() -> dict[str, str]:
    if not LOCK.exists():
        raise ValueError("Final predictions are blocked until independent labels are frozen")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    if lock.get("labels_sha256") != _sha(LABELS):
        raise ValueError("Human label file changed after freeze")
    if (lock.get("frozen_copy") != FROZEN_LABELS.name
            or not FROZEN_LABELS.exists()
            or lock.get("frozen_copy_sha256") != _sha(FROZEN_LABELS)
            or lock["labels_sha256"] != lock["frozen_copy_sha256"]):
        raise ValueError("Frozen human label copy changed or is missing")
    return _validated_labels()


def _protocol_snapshot() -> dict[str, str]:
    paths = [PROTOCOL, ROOT / "FOLLOWUP_RUBRIC.md", ROOT / "ADJUDICATION_RUBRIC.md",
             *(ROOT / "datasets" / "evaluation" / name for name in (
                 "followup_cases.py", "followup_cases_sample.py", "personas.py",
                 "personas_sample.py",
             ))]
    return {path.relative_to(ROOT).as_posix(): _sha(path) for path in paths}


def _model_metadata(events: list[dict]) -> dict[str, list[str]]:
    return {
        "models_requested": sorted({event["model"] for event in events
                                    if event.get("operation") == "generate_structured"
                                    and event.get("model")}),
        "models_returned": sorted({event["model"] for event in events
                                   if event.get("operation") == "generate_structured_completed"
                                   and event.get("model")}),
    }


def _client_region(pool: str) -> str:
    region = os.environ.get("INTERMIND_EVAL_REGION", "").strip()
    if pool == "final" and not region:
        raise ValueError("Final latency provenance requires INTERMIND_EVAL_REGION")
    return region or "unspecified"


def freeze_protocol() -> None:
    _require_frozen_labels()
    if PROTOCOL_LOCK.exists():
        raise FileExistsError("Protocol is already frozen; do not overwrite its lock")
    if "**Version:** 1.0 · **Status:** frozen · **Frozen:** yes" not in PROTOCOL.read_text(
        encoding="utf-8"
    ):
        raise ValueError("Finalize protocol version and status before freezing")
    with PROTOCOL_LOCK.open("x", encoding="utf-8") as output:
        json.dump({"version": "1.0", "frozen_at_utc": datetime.now(UTC).isoformat(),
                   "files_sha256": _protocol_snapshot(), "labels_sha256": _sha(LABELS)},
                  output, indent=2)
        output.write("\n")
    os.chmod(PROTOCOL_LOCK, 0o444)


def _require_frozen_protocol() -> dict:
    if not PROTOCOL_LOCK.exists():
        raise ValueError("Paid evaluation is blocked until the protocol is frozen")
    lock = json.loads(PROTOCOL_LOCK.read_text(encoding="utf-8"))
    if (lock.get("version") != "1.0" or lock.get("files_sha256") != _protocol_snapshot()
            or lock.get("labels_sha256") != _sha(LABELS)):
        raise ValueError("Frozen protocol, rubric, dataset, or labels changed")
    return lock


def _plan(job, *, first_two: bool = False):
    from app.domain.interview_plan import (
        CoverageTarget,
        EvidenceSource,
        InterviewPlan,
        QuestionCategory,
        RequirementLevel,
    )
    from app.domain.occupation import OccupationMatch
    from app.services.target_identity import target_question_id

    cases = job.cases[:2] if first_two else job.cases
    targets = [CoverageTarget(
        id=target_question_id(job.jd_id, row[0], row[1]), target=row[1],
        category=QuestionCategory(row[0]), requirement_level=RequirementLevel.REQUIRED,
        source=EvidenceSource.JOBSPEC, priority=index,
        grounding=f"Job description: {row[1]}",
    ) for index, row in enumerate(cases)]
    return InterviewPlan(
        job_id=job.jd_id, role_title=job.role_title,
        occupation_match=OccupationMatch(
            onet_soc_code="00-0000.00", title="Evaluation fixture", score=0
        ),
        onet_grounding_used=False, coverage_targets=targets,
    )


async def _followup_run(cases, evaluator, on_row=None) -> list[dict]:
    from app.domain.evaluation import resolve_follow_up_decision

    rows = []
    for case in cases:
        raw = await evaluator.evaluate(
            question_text=case.question, category=followup_cases.category_for(case.target),
            target=case.target,
            answer=case.answer, prior_exchange=list(case.prior_exchange),
        )
        decision = resolve_follow_up_decision(
            raw, follow_ups_used=1 if case.prior_exchange else 0
        )
        rows.append({"case_id": case.case_id, "prediction": decision.decision.value,
                     "raw_evaluation": raw.model_dump(mode="json")})
        if on_row is not None:
            on_row("followup", rows[-1])
    return rows


async def _persona_run(
    jobs, candidates, evaluator, reporter, on_row=None
) -> tuple[list[dict], list[dict]]:
    from app.domain.interview import InterviewState, InterviewStatus
    from app.services.cross_target_evidence import resolve_cross_target_evidence

    by_job = {job.jd_id: job for job in jobs}
    scores: list[dict] = []
    evidence: list[dict] = []
    for candidate in candidates:
        plan = _plan(by_job[candidate.jd_id])
        target_by_name = {target.target: target for target in plan.coverage_targets}
        history: list[dict] = []
        assessed: list[str] = []
        hints: dict[str, dict] = {}
        for answer in candidate.answers:
            target = target_by_name[answer.target]
            other_targets = [
                (other.category.value, other.target) for other in plan.coverage_targets
                if other.id != target.id and other.id not in assessed
            ]
            evaluation = await evaluator.evaluate(
                question_text=answer.question, category=target.category.value,
                target=target.target, grounding=target.grounding, answer=answer.answer,
                other_targets=other_targets,
            )
            # Fixed-turn replay: each persona supplies a byte-fixed answer for every target.
            # We preserve the model's evaluation but do not let adaptive routing skip targets.
            history.append({"question_id": target.id, "root_question_id": target.id,
                            "question": answer.question, "answer": answer.answer,
                            "evaluation": evaluation.model_dump(mode="json")})
            if target.id not in assessed:
                assessed.append(target.id)
            if evaluation.cross_target_evidence:
                resolution = resolve_cross_target_evidence(
                    coverage_targets=[
                        {"id": other.id, "target": other.target,
                         "category": other.category.value}
                        for other in plan.coverage_targets
                    ],
                    current_target_id=target.id,
                    assessed_target_ids=assessed,
                    cross_target_evidence=[item.model_dump(mode="json")
                                           for item in evaluation.cross_target_evidence],
                    existing_hints=hints, answer=answer.answer,
                )
                history.extend(resolution.history_entries)
                assessed.extend(resolution.newly_assessed_ids)
                hints = resolution.updated_hints
        state = InterviewState(
            job_id=plan.job_id, status=InterviewStatus.COMPLETED,
            history=history,
            asked_question_ids=[t["question_id"] for t in history
                                if t.get("assessment_method", "direct") == "direct"],
        )
        report = await reporter.generate(
            interview_id=candidate.persona_id, plan=plan, state=state,
        )
        scores.append({"jd_id": candidate.jd_id, "persona_id": candidate.persona_id,
                       "tier": candidate.tier, "score": report.overall_score,
                       "recommendation": report.recommendation.value,
                       "report": report.model_dump(mode="json")})
        evidence.extend(extract_evidence(report, state))
        if on_row is not None:
            on_row("persona", scores[-1])
    return scores, evidence


def _latency_app(client):
    """Real answer route/graph/repositories, isolated in-memory; auth setup is outside timing."""
    from fastapi import FastAPI

    from app.agents.interview_graph import build_interview_graph
    from app.api.deps import get_interview_session_service, get_llm_client
    from app.api.errors import register_exception_handlers
    from app.api.recruiter_session import RecruiterSessionStore
    from app.api.routes import interviews
    from app.core.rate_limit import RateLimiter
    from app.repositories.in_memory import (
        InMemoryActivityRepository,
        InMemoryCandidateRepository,
        InMemoryInterviewPlanRepository,
        InMemoryInterviewReportRepository,
        InMemoryInterviewSessionRepository,
        InMemoryJobRepository,
    )
    from app.services.answer_evaluation import AnswerEvaluationService
    from app.services.interview_session import InterviewSessionService
    from app.services.question_generation import QuestionGenerationService

    app = FastAPI()
    app.state.job_repository = InMemoryJobRepository()
    app.state.candidate_repository = InMemoryCandidateRepository()
    app.state.interview_plan_repository = InMemoryInterviewPlanRepository()
    app.state.interview_session_repository = InMemoryInterviewSessionRepository(
        app.state.job_repository
    )
    app.state.interview_report_repository = InMemoryInterviewReportRepository()
    app.state.activity_repository = InMemoryActivityRepository(app.state.job_repository)
    app.state.rate_limiter = RateLimiter()
    app.state.recruiter_session_store = RecruiterSessionStore(ttl_seconds=3600)
    graph = build_interview_graph(
        AnswerEvaluationService(client), QuestionGenerationService(client)
    )
    service = InterviewSessionService(graph, app.state.interview_plan_repository,
                                      app.state.interview_session_repository,
                                      app.state.candidate_repository)
    app.dependency_overrides[get_llm_client] = lambda: client
    app.dependency_overrides[get_interview_session_service] = lambda: service
    register_exception_handlers(app)
    app.include_router(interviews.router)
    return app, service


def _usable_advance_count(rows: list[dict]) -> int:
    return sum(row["path"] == "advance" and not row.get("warmup")
               and not row.get("retried") for row in rows)


async def _latency_run(
    client, job, *, target_n: int, max_sessions: int, on_row=None
) -> list[dict]:
    import httpx

    from app.repositories.ports import StoredJob

    app, service = _latency_app(client)
    plan = _plan(job, first_two=True)
    await app.state.job_repository.add(StoredJob(
        id=job.jd_id, recruiter_id="evaluation-recruiter",
        job_description=job.text, job_spec={"role_title": job.role_title},
    ))
    await app.state.interview_plan_repository.add(plan)
    rows: list[dict] = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://eval.local"
    ) as http:
        for index in range(max_sessions):
            interview_id, state = await service.start(job.jd_id, f"Latency {index}")
            session = await app.state.interview_session_repository.get(interview_id)
            answer = job.cases[0][3]
            trace = getattr(client, "_trace", None)
            trace_start = len(trace.events) if trace is not None else 0
            started = time.perf_counter()
            response = await http.post(f"/interviews/{interview_id}/answers",
                                       json={"turn_id": state.current_turn_id, "answer": answer},
                                       headers={"Authorization": f"Bearer {session.access_token}"})
            elapsed = time.perf_counter() - started
            if response.status_code != 200:
                raise RuntimeError(f"Answer endpoint returned HTTP {response.status_code}")
            body = response.json()
            path = (
                "follow_up" if body["current_question_is_follow_up"] else
                "advance" if body["current_question_id"] not in (None, state.current_question_id)
                else "finish"
            )
            request_events = trace.events[trace_start:] if trace is not None else []
            retried = sum(
                event.operation == "generate_structured_completed"
                and event.details.get("schema") == "GeneratedQuestionSet"
                for event in request_events
            ) > 1
            rows.append({"seconds": elapsed, "path": path, "warmup": index < 3,
                         "retried": retried})
            if on_row is not None:
                on_row("latency", rows[-1])
            if _usable_advance_count(rows) >= target_n:
                break
    if _usable_advance_count(rows) < target_n:
        raise RuntimeError("Insufficient advance-path samples; retain the run, do not report p95")
    return rows


async def run(pool: str, *, allow_paid: bool) -> Path:
    if not allow_paid:
        raise ValueError("Paid API calls require the explicit --allow-paid flag")
    if pool == "final":
        _require_frozen_labels()  # before any OpenAI client or result directory exists
        cases, jobs, candidates = followup_cases.CASES, personas.JOBS, personas.PERSONAS
        latency_target, latency_max = 100, 130
    else:
        cases, jobs, candidates = pilot_cases.FOLLOWUPS, pilot_cases.JOBS, pilot_cases.PERSONAS
        latency_target, latency_max = 3, 10
    _require_frozen_protocol()  # pilot cannot alter the final dataset or protocol unnoticed
    client_region = _client_region(pool)

    from app.core.config import get_settings
    from app.observability.trace import TraceRecorder
    from app.services.answer_evaluation import AnswerEvaluationService
    from app.services.report_generation import ReportGenerationService
    from app.services.report_narrative import ReportNarrativeService

    settings = get_settings()
    if settings.llm_provider != "openai" or not settings.openai_api_key:
        raise ValueError("Live evaluation requires configured LLM_PROVIDER=openai and an API key")
    if settings.openai_model != PRICING["model"]:
        raise ValueError(
            "Price table does not match configured model; update verified pricing first"
        )
    trace = TraceRecorder()
    call_cap = 80 if pool == "pilot" else 750
    llm = _budgeted_client_class()(
        api_key=settings.openai_api_key, model=settings.openai_model,
        trace=trace, max_calls=call_cap,
    )
    # The protocol excludes retries from latency. Disable SDK transport retries in this
    # measurement client; application-level question retries are detected per request.
    llm._client = llm._client.with_options(max_retries=0)
    evaluator = AnswerEvaluationService(llm)
    reporter = ReportGenerationService(ReportNarrativeService(llm))
    began = datetime.now(UTC)
    result_dir = ROOT / "results" / f"{began:%Y%m%dT%H%M%SZ}-{pool}"
    result_dir.mkdir(parents=True, exist_ok=False)
    _json(result_dir / "run_state.json", {
        "status": "incomplete", "started_utc": began.isoformat(),
    })

    def save_progress(kind: str, row: dict) -> None:
        with (result_dir / "progress.jsonl").open("a", encoding="utf-8") as output:
            output.write(json.dumps({"kind": kind, "row": row}, ensure_ascii=False) + "\n")

    try:
        followups = await _followup_run(cases, evaluator, on_row=save_progress)
        scores, evidence = await _persona_run(
            jobs, candidates, evaluator, reporter, on_row=save_progress
        )
        latency_started = datetime.now(UTC)
        latency = await _latency_run(
            llm, jobs[0], target_n=latency_target, max_sessions=latency_max,
            on_row=save_progress,
        )
        latency_ended = datetime.now(UTC)
    except Exception as exc:
        _json(result_dir / "run_state.json", {
            "status": "failed", "started_utc": began.isoformat(),
            "failed_at_utc": datetime.now(UTC).isoformat(), "error_type": type(exc).__name__,
        })
        raise
    finally:
        _json(result_dir / "llm_trace.json", [
            {"operation": event.operation, **event.details} for event in trace.events
        ])
    ended = datetime.now(UTC)
    events = [{"operation": event.operation, **event.details} for event in trace.events]
    cost = token_cost(events, PRICING["input_per_million_usd"],
                      PRICING["output_per_million_usd"],
                      PRICING["cached_input_per_million_usd"])
    cost_by_stage = {
        schema: token_cost(
            [event for event in events if event.get("schema") == schema],
            PRICING["input_per_million_usd"], PRICING["output_per_million_usd"],
            PRICING["cached_input_per_million_usd"],
        )
        for schema in sorted({event.get("schema") for event in events if event.get("schema")})
    }
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.strip()
    dirty = bool(subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
        text=True, check=True,
    ).stdout.strip())
    source_paths = [
        ROOT / "run_interview_eval.py", ROOT / "harness" / "metrics.py",
        ROOT / "harness" / "evidence.py", ROOT / "harness" / "grounding.py",
        ROOT.parent / "app" / "llm" / "openai_client.py",
        ROOT.parent / "app" / "domain" / "evaluation.py",
        ROOT.parent / "app" / "services" / "report_scoring.py",
        *(ROOT.parent / "app" / "llm" / "prompts" / name for name in (
            "answer_evaluation_v1.md", "interview_questions_v1.md",
            "interview_report_v1.md",
        )),
    ]
    _json(result_dir / "metadata.json", {
        "pool": pool, "started_utc": began.isoformat(), "ended_utc": ended.isoformat(),
        "git_sha": sha, "git_worktree_dirty": dirty,
        "source_sha256": {str(path.relative_to(ROOT.parent)): _sha(path)
                          for path in source_paths},
        "protocol_sha256": _sha(ROOT / "PROTOCOL.md"),
        "labels_sha256": _sha(LABELS) if pool == "final" else None,
        "model_configured": settings.openai_model, "temperature": "unset (API default)",
        **_model_metadata(events),
        "repository": "in-memory", "latency_transport": "httpx ASGI in-process, sequential",
        "client_environment": platform.platform(),
        "client_region": client_region,
        "latency_started_utc": latency_started.isoformat(),
        "latency_ended_utc": latency_ended.isoformat(),
        "sdk_transport_retries": 0,
        "pricing": PRICING, "usage_and_cost": cost,
        "api_call_cap": call_cap, "api_calls_attempted": llm.calls_attempted,
        "usage_and_cost_by_stage": cost_by_stage,
        "dataset_sha256": {"followup": _sha(ROOT / "datasets" / "evaluation" / "followup_cases.py")
                           if pool == "final" else _sha(ROOT / "datasets" / "pilot" / "cases.py"),
                           "personas": _sha(ROOT / "datasets" / "evaluation" / "personas.py")
                           if pool == "final" else _sha(ROOT / "datasets" / "pilot" / "cases.py"),
                           "followup_sample": _sha(
                               ROOT / "datasets" / "evaluation" / "followup_cases_sample.py"
                           ) if pool == "final" else None,
                           "persona_sample": _sha(
                               ROOT / "datasets" / "evaluation" / "personas_sample.py"
                           ) if pool == "final" else None},
    })
    _json(result_dir / "followup_predictions.json", followups)
    _json(result_dir / "persona_reports.json", scores)
    _json(result_dir / "evidence_internal.json", evidence)
    _json(result_dir / "latency_requests.json", latency)
    blind = blinded_adjudication(evidence)
    _csv(result_dir / "evidence_adjudication_blind.csv",
         ["evidence_id", "evidence_string", "source_answers", "verdict"],
         [{**row, "source_answers": json.dumps(row["source_answers"])} for row in blind])
    _json(result_dir / "run_state.json", {
        "status": "complete", "started_utc": began.isoformat(),
        "ended_utc": ended.isoformat(),
    })
    print(f"{pool} run recorded at {result_dir}; {len(blind)} evidence items need blind review")
    return result_dir


def aggregate(result_dir: Path) -> dict:
    state = json.loads((result_dir / "run_state.json").read_text(encoding="utf-8"))
    if state.get("status") != "complete":
        raise ValueError("Incomplete or failed run cannot produce final metrics")
    metadata = json.loads((result_dir / "metadata.json").read_text(encoding="utf-8"))
    if metadata["pool"] != "final":
        raise ValueError("Pilot results must never be reported as final metrics")
    labels = _require_frozen_labels()
    protocol_lock = _require_frozen_protocol()
    if metadata["protocol_sha256"] != protocol_lock["files_sha256"]["PROTOCOL.md"]:
        raise ValueError("Run and frozen protocol do not match")
    if metadata["labels_sha256"] != _sha(LABELS):
        raise ValueError("Run and frozen human labels do not match")
    followups = json.loads((result_dir / "followup_predictions.json").read_text(encoding="utf-8"))
    expected_cases = {case.case_id: case for case in followup_cases.CASES}
    prediction_ids = [row["case_id"] for row in followups]
    if (len(prediction_ids) != len(expected_cases)
            or len(set(prediction_ids)) != len(prediction_ids)
            or set(prediction_ids) != set(expected_cases)):
        raise ValueError("Final predictions must contain every frozen follow-up case once")
    scores = json.loads((result_dir / "persona_reports.json").read_text(encoding="utf-8"))
    evidence = json.loads((result_dir / "evidence_internal.json").read_text(encoding="utf-8"))
    latency = json.loads((result_dir / "latency_requests.json").read_text(encoding="utf-8"))
    adjudication = _read_csv(result_dir / "evidence_adjudication_blind.csv")
    verdicts = {row["evidence_id"]: row["verdict"].strip() for row in adjudication}
    if len(verdicts) != len(adjudication):
        raise ValueError("Duplicate adjudication IDs")
    from evals.harness.grounding import classify

    sensitivity = {
        f"theta_{theta:.2f}": sum(
            classify(row["evidence_string"], row["source_answers"], theta=theta).auto_supported
            for row in evidence
        ) / len(evidence)
        for theta in (.70, .80, .90)
    } if evidence else {}
    report = {
        "follow_up": followup_metrics(
            [(labels[row["case_id"]], row["prediction"]) for row in followups],
            cluster_ids=[f"{expected_cases[row['case_id']].target}\0"
                         f"{expected_cases[row['case_id']].question}" for row in followups],
        ),
        "evidence": {**traceability_metrics(evidence, verdicts),
                     "automatic_verification_sensitivity": sensitivity},
        "latency": latency_metrics(latency),
        "discrimination": discrimination_metrics(scores),
        "usage_and_cost": metadata["usage_and_cost"],
        "run_metadata": {key: metadata[key] for key in (
            "started_utc", "ended_utc", "model_configured", "models_requested",
            "models_returned",
            "repository", "latency_transport", "git_sha", "protocol_sha256")},
    }
    output = result_dir / "metrics.json"
    if output.exists():
        raise FileExistsError("Final metrics already exist; results are immutable")
    _json(output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("export-labels")
    sub.add_parser("freeze-labels")
    sub.add_parser("freeze-protocol")
    for name in ("pilot", "final"):
        sub.add_parser(name).add_argument("--allow-paid", action="store_true")
    sub.add_parser("aggregate").add_argument("result_dir", type=Path)
    args = parser.parse_args()
    if args.command == "export-labels":
        export_labels()
    elif args.command == "freeze-labels":
        freeze_labels()
    elif args.command == "freeze-protocol":
        freeze_protocol()
    elif args.command in {"pilot", "final"}:
        asyncio.run(run(args.command, allow_paid=args.allow_paid))
    else:
        print(json.dumps(aggregate(args.result_dir), indent=2))


if __name__ == "__main__":
    main()
