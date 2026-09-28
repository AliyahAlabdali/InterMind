"""Real PostgreSQL migration/transaction/restart tests against a disposable local cluster.

Never reads DATABASE_URL or connects to an existing database. No LLM/Azure calls.
"""

import asyncio
import importlib.util
import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import StaleInterviewTurn
from app.db.models import Base
from app.domain.job import JobSpec
from app.domain.recruiter import Recruiter
from app.repositories.ports import StoredJob
from app.repositories.sql import (
    SqlCandidateRepository,
    SqlInterviewPlanRepository,
    SqlInterviewReportRepository,
    SqlInterviewSessionRepository,
    SqlJobRepository,
    SqlRecruiterRepository,
)
from tests.conftest import FIXTURES
from tests.unit.test_interview_session_service import (
    DETAILED_ANSWER,
    SHORT_ANSWER,
    _make_plan,
    _make_service,
)


@pytest.fixture(scope="session")
def isolated_postgres(tmp_path_factory):
    executable = shutil.which("initdb")
    if not executable:
        installations = Path("C:/Program Files/PostgreSQL")
        candidates = sorted(installations.glob("*/bin/initdb.exe"), reverse=True)
        executable = str(candidates[0]) if candidates else None
    if not executable:
        pytest.skip("Local PostgreSQL binaries are needed for isolated database tests")
    binaries = Path(executable).parent
    directory = tmp_path_factory.mktemp("intermind-postgres")
    data = directory / "cluster"
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    subprocess.run([executable, "-D", str(data), "-A", "trust", "-U", "intermind_test"],
                   check=True, capture_output=True, **flags)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    pg_ctl = str(binaries / ("pg_ctl.exe" if sys.platform == "win32" else "pg_ctl"))
    subprocess.run([pg_ctl, "-D", str(data), "-l", str(directory / "server.log"),
                    "-o", f"-h 127.0.0.1 -p {port}", "-w", "start"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                   stdin=subprocess.DEVNULL, timeout=60, **flags)
    try:
        yield f"postgresql+asyncpg://intermind_test@127.0.0.1:{port}/postgres"
    finally:
        subprocess.run([pg_ctl, "-D", str(data), "-m", "fast", "-w", "stop"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                       stdin=subprocess.DEVNULL, timeout=60, **flags)


def migration(name):
    path = Path(__file__).parents[2] / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def sql_engine(isolated_postgres):
    engine = create_async_engine(isolated_postgres)
    async with engine.begin() as connection:
        def upgrade(sync):
            # Isolate each test in its own schema; the cluster itself is already disposable.
            sync.execute(text("DROP SCHEMA public CASCADE"))
            sync.execute(text("CREATE SCHEMA public"))
            context = MigrationContext.configure(sync)
            with Operations.context(context):
                migration("c6505f42e5f3_recruiter_accounts_and_owned_resources.py").upgrade()
                # A real old-schema row survives the additive migration untouched.
                sync.execute(text("INSERT INTO recruiters VALUES "
                                  "('legacy','legacy@intermind.test','test-hash',now())"))
                migration("f3a821d9c604_durable_interview_snapshot.py").upgrade()
            assert sync.scalar(text("SELECT count(*) FROM recruiters WHERE id='legacy'")) == 1
            assert compare_metadata(context, Base.metadata) == []
            assert inspect(sync).get_columns("interview_sessions")[-1]["name"] == "runtime_snapshot"
        await connection.run_sync(upgrade)
    yield engine
    await engine.dispose()


async def sql_service(engine):
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    recruiter = Recruiter(email="sql@intermind.test", password_hash="test-hash")
    await SqlRecruiterRepository(sessions).add(recruiter)
    spec = JobSpec.model_validate(json.loads((FIXTURES / "sample_jobspec.json").read_text()))
    job = StoredJob(recruiter_id=recruiter.id, job_description="offline test", job_spec=spec)
    await SqlJobRepository(sessions).add(job)
    service = _make_service()
    service.session_repo = SqlInterviewSessionRepository(sessions)
    service.candidate_repo = SqlCandidateRepository(sessions)
    service.plan_repo = SqlInterviewPlanRepository(sessions)
    await service.plan_repo.add(_make_plan(job.id))
    return service, job.id, recruiter.id, sessions


def restarted(service, sessions):
    fresh = _make_service()
    fresh.session_repo = SqlInterviewSessionRepository(sessions)
    fresh.candidate_repo = SqlCandidateRepository(sessions)
    fresh.plan_repo = SqlInterviewPlanRepository(sessions)
    return fresh


async def test_completed_before_first_report_recovers_from_postgres(sql_engine):
    from app.api.routes.interviews import _get_or_generate_report
    from app.llm.fake_client import FakeLLMClient
    from app.services.report_generation import ReportGenerationService
    from app.services.report_narrative import ReportNarrativeService
    service, job_id, owner, sessions = await sql_service(sql_engine)
    iid, state = await service.start(job_id)
    for _ in range(3):
        state = await service.submit_answer(iid, DETAILED_ANSWER, state.current_turn_id)
    assert state.status.value == "completed"
    fresh = restarted(service, sessions)
    restored = await fresh.get_state(iid)
    assert restored.history == state.history
    assert restored.status.value == "completed"
    from app.api.routes.speech import _reject_if_completed
    from app.core.exceptions import InterviewAlreadyCompleted, InterviewNotFound
    with pytest.raises(InterviewAlreadyCompleted):
        await _reject_if_completed(fresh, iid)
    await fresh.session_repo.get_for_recruiter(iid, owner)
    with pytest.raises(InterviewNotFound):
        await fresh.session_repo.get_for_recruiter(iid, "unrelated-owner")
    reports = SqlInterviewReportRepository(sessions)
    report = await _get_or_generate_report(
        interview_id=iid, session_service=fresh, plan_repo=fresh.plan_repo,
        report_repo=reports,
        report_service=ReportGenerationService(narrative=ReportNarrativeService(llm=FakeLLMClient())),
    )
    assert len(report.question_evaluations) == 3
    assert (await reports.get(iid)) == report


async def test_active_follow_up_and_turn_identity_recover(sql_engine):
    service, job_id, _, sessions = await sql_service(sql_engine)
    iid, initial = await service.start(job_id)
    follow_up = await service.submit_answer(iid, SHORT_ANSWER, initial.current_turn_id)
    fresh = restarted(service, sessions)
    recovered = await fresh.get_state(iid)
    assert recovered == follow_up
    assert recovered.current_turn_id != initial.current_turn_id
    with pytest.raises(StaleInterviewTurn):
        await fresh.submit_answer(iid, SHORT_ANSWER, initial.current_turn_id)
    advanced = await fresh.submit_answer(iid, DETAILED_ANSWER, recovered.current_turn_id)
    assert advanced.current_question_id == "q2"
    assert len(advanced.history) == 2
    assert advanced.history[1]["question"] == follow_up.current_question_text


async def test_separate_process_graphs_serialize_duplicates(sql_engine):
    service, job_id, _, sessions = await sql_service(sql_engine)
    iid, state = await service.start(job_id)
    other = restarted(service, sessions)
    results = await asyncio.gather(
        service.submit_answer(iid, DETAILED_ANSWER, state.current_turn_id),
        other.submit_answer(iid, DETAILED_ANSWER, state.current_turn_id),
        return_exceptions=True,
    )
    assert sum(isinstance(result, StaleInterviewTurn) for result in results) == 1
    assert len((await other.get_state(iid)).history) == 1


async def test_snapshot_transaction_rolls_back_and_graph_failure_preserves_turn(sql_engine):
    from unittest.mock import AsyncMock
    service, job_id, _, sessions = await sql_service(sql_engine)
    iid, initial = await service.start(job_id)
    with pytest.raises(RuntimeError):
        async with service.session_repo.locked(iid) as record:
            record.runtime_snapshot = None
            raise RuntimeError("rollback")
    assert await service.get_state(iid) == initial
    service.graph.ainvoke = AsyncMock(side_effect=RuntimeError("offline interruption"))
    with pytest.raises(RuntimeError):
        await service.submit_answer(iid, DETAILED_ANSWER, initial.current_turn_id)
    fresh = restarted(service, sessions)
    assert await fresh.get_state(iid) == initial
    accepted = await fresh.submit_answer(iid, DETAILED_ANSWER, initial.current_turn_id)
    assert len(accepted.history) == 1


async def test_concurrent_report_generation_across_separate_graphs(sql_engine):
    from app.api.routes.interviews import _get_or_generate_report
    from app.llm.fake_client import FakeLLMClient
    from app.services.report_generation import ReportGenerationService
    from app.services.report_narrative import ReportNarrativeService
    service, job_id, _, sessions = await sql_service(sql_engine)
    iid, state = await service.start(job_id)
    for _ in range(3):
        state = await service.submit_answer(iid, DETAILED_ANSWER, state.current_turn_id)
    generator = ReportGenerationService(narrative=ReportNarrativeService(llm=FakeLLMClient()))
    generate = generator.generate
    calls = 0

    async def slow_generate(**kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(.02)
        return await generate(**kwargs)

    generator.generate = slow_generate
    reports = SqlInterviewReportRepository(sessions)
    first, second = await asyncio.gather(*[
        _get_or_generate_report(
            interview_id=iid, session_service=worker, plan_repo=worker.plan_repo,
            report_repo=reports, report_service=generator,
        ) for worker in (service, restarted(service, sessions))
    ])
    assert calls == 1
    assert first == second
