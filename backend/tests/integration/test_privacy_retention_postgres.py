"""Retention and erasure checks against a disposable local PostgreSQL cluster."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text, update

from app.core.exceptions import InterviewNotFound
from app.db.models import (
    ActivityEventRow,
    CandidateRow,
    InterviewReportRow,
    InterviewSessionRow,
    JobRow,
    RecruiterRow,
)
from app.domain.activity import ActivityEvent, ActivityType
from app.privacy.retention import (
    delete_interview_for_recruiter,
    purge_expired_interviews,
    purge_orphan_data,
)
from app.repositories.sql import SqlActivityRepository
from tests.integration.test_durable_interview_postgres import (  # noqa: F401
    isolated_postgres,
    migration,
    sql_engine,
    sql_service,
)


@pytest.mark.asyncio
async def test_purge_uses_latest_report_and_preserves_recent_interview(sql_engine):  # noqa: F811
    service, job_id, owner, sessions = await sql_service(sql_engine)
    old_id, _ = await service.start(job_id, "Old candidate")
    report_id, _ = await service.start(job_id, "Reported candidate")
    recent_id, _ = await service.start(job_id, "Recent candidate")
    now = datetime.now(UTC)
    old = now - timedelta(days=91)
    async with sessions() as session, session.begin():
        await session.execute(update(InterviewSessionRow).where(
            InterviewSessionRow.id.in_([old_id, report_id])
        ).values(last_activity_at=old))
        session.add(InterviewReportRow(
            interview_id=report_id, report={"synthetic": True}, created_at=now,
        ))
        old_candidate = (await session.get(InterviewSessionRow, old_id)).candidate_id
    assert await purge_expired_interviews(sessions, now=now) == 1
    async with sessions() as session:
        assert await session.get(InterviewSessionRow, old_id) is None
        assert await session.get(CandidateRow, old_candidate) is None
        assert await session.get(InterviewSessionRow, report_id) is not None
        assert await session.get(InterviewSessionRow, recent_id) is not None
    with pytest.raises(InterviewNotFound):
        await delete_interview_for_recruiter(sessions, interview_id=report_id, recruiter_id="other")
    await delete_interview_for_recruiter(sessions, interview_id=report_id, recruiter_id=owner)
    async with sessions() as session:
        assert await session.get(InterviewReportRow, report_id) is None
        assert await session.get(InterviewSessionRow, report_id) is None


@pytest.mark.asyncio
async def test_activity_cannot_reappear_after_erasure(sql_engine):  # noqa: F811
    service, job_id, owner, sessions = await sql_service(sql_engine)
    interview_id, _ = await service.start(job_id, "Synthetic candidate")
    event = ActivityEvent(
        type=ActivityType.INTERVIEW_STARTED,
        interview_id=interview_id,
        job_id=job_id,
        candidate_name="Synthetic candidate",
    )
    repo = SqlActivityRepository(sessions)
    await repo.add(event)
    await delete_interview_for_recruiter(sessions, interview_id=interview_id, recruiter_id=owner)
    await repo.add(ActivityEvent(
        type=ActivityType.INTERVIEW_STARTED,
        interview_id=interview_id,
        job_id=job_id,
        candidate_name="Synthetic candidate",
    ))
    async with sessions() as session:
        assert (await session.scalars(select(ActivityEventRow).where(
            ActivityEventRow.interview_id == interview_id
        ))).first() is None


@pytest.mark.asyncio
async def test_orphan_cleanup_is_aged_and_bounded(sql_engine):  # noqa: F811
    _, job_id, _, sessions = await sql_service(sql_engine)
    now = datetime.now(UTC)
    old = now - timedelta(days=91)
    async with sessions() as session, session.begin():
        session.add_all([
            CandidateRow(id="aged-candidate", name="Synthetic", email="", created_at=old),
            CandidateRow(id="new-candidate", name="Synthetic", email="", created_at=now),
            ActivityEventRow(id="aged-activity", type="started", interview_id="missing",
                             job_id=job_id, candidate_name="Synthetic", target=None,
                             created_at=old),
        ])
    assert await purge_orphan_data(sessions, now=now) == (1, 1)
    async with sessions() as session:
        assert await session.get(CandidateRow, "aged-candidate") is None
        assert await session.get(ActivityEventRow, "aged-activity") is None
        assert await session.get(CandidateRow, "new-candidate") is not None


@pytest.mark.asyncio
async def test_recruiter_cannot_delete_another_tenants_interview(sql_engine):  # noqa: F811
    _, _, first_owner, sessions = await sql_service(sql_engine)
    async with sessions() as session, session.begin():
        session.add(RecruiterRow(id="other-owner", email="other@intermind.test",
                                 password_hash="synthetic-hash"))
        await session.flush()
        session.add(JobRow(id="other-job", recruiter_id="other-owner",
                           job_description="synthetic role", job_spec={}))
        await session.flush()
        session.add(CandidateRow(id="other-candidate", name="Synthetic", email=""))
        session.add(InterviewSessionRow(
            id="other-interview", job_id="other-job", candidate_id="other-candidate",
            access_token="synthetic-token", runtime_snapshot={},
        ))
    with pytest.raises(InterviewNotFound):
        await delete_interview_for_recruiter(
            sessions, interview_id="other-interview", recruiter_id=first_owner
        )
    async with sessions() as session:
        assert await session.get(InterviewSessionRow, "other-interview") is not None
        assert await session.get(CandidateRow, "other-candidate") is not None


@pytest.mark.asyncio
async def test_recent_activity_extends_retention(sql_engine):  # noqa: F811
    service, job_id, _, sessions = await sql_service(sql_engine)
    interview_id, _ = await service.start(job_id, "Synthetic candidate")
    now = datetime.now(UTC)
    async with sessions() as session, session.begin():
        await session.execute(update(InterviewSessionRow).where(
            InterviewSessionRow.id == interview_id
        ).values(last_activity_at=now - timedelta(days=91)))
    await SqlActivityRepository(sessions).add(ActivityEvent(
        type=ActivityType.INTERVIEW_STARTED,
        interview_id=interview_id,
        job_id=job_id,
        candidate_name="Synthetic candidate",
        created_at=now,
    ))
    assert await purge_expired_interviews(sessions, now=now) == 0
    async with sessions() as session:
        row = await session.get(InterviewSessionRow, interview_id)
        assert row is not None and row.last_activity_at == now


@pytest.mark.asyncio
async def test_purge_skips_concurrent_interview_lock(sql_engine):  # noqa: F811
    service, job_id, _, sessions = await sql_service(sql_engine)
    interview_id, _ = await service.start(job_id, "Synthetic candidate")
    now = datetime.now(UTC)
    async with sessions() as session, session.begin():
        await session.execute(update(InterviewSessionRow).where(
            InterviewSessionRow.id == interview_id
        ).values(last_activity_at=now - timedelta(days=91)))
    async with sessions() as blocker, blocker.begin():
        await blocker.scalar(select(InterviewSessionRow).where(
            InterviewSessionRow.id == interview_id
        ).with_for_update())
        assert await asyncio.wait_for(
            purge_expired_interviews(sessions, now=now), timeout=5
        ) == 0
    assert await purge_expired_interviews(sessions, now=now) == 1


@pytest.mark.asyncio
async def test_retention_migration_backfills_latest_historical_report(sql_engine):  # noqa: F811
    old = datetime.now(UTC) - timedelta(days=100)
    report_time = datetime.now(UTC) - timedelta(days=10)

    async with sql_engine.begin() as connection:
        def exercise(sync):
            context = MigrationContext.configure(sync)
            with Operations.context(context):
                revision = migration("d91e5a7c2b40_interview_retention_clock.py")
                revision.downgrade()
                sync.execute(text("""
                    INSERT INTO jobs (id, recruiter_id, job_description, job_spec, created_at)
                    VALUES ('old-job', 'legacy', 'synthetic', '{}', :old)
                """), {"old": old})
                sync.execute(text("""
                    INSERT INTO candidates (id, name, email, created_at)
                    VALUES ('old-candidate', 'Synthetic', '', :old)
                """), {"old": old})
                sync.execute(text("""
                    INSERT INTO interview_sessions
                        (id, job_id, candidate_id, access_token, created_at)
                    VALUES ('old-interview', 'old-job', 'old-candidate', 'synthetic', :old)
                """), {"old": old})
                sync.execute(text("""
                    INSERT INTO interview_reports (interview_id, report, created_at)
                    VALUES ('old-interview', '{}', :report_time)
                """), {"report_time": report_time})
                revision.upgrade()
                return sync.scalar(text("""
                    SELECT last_activity_at FROM interview_sessions
                    WHERE id = 'old-interview'
                """))

        backfilled = await connection.run_sync(exercise)
    assert backfilled == report_time
