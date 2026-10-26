"""Transactional deletion of interview data and bounded retention sweeps.

The PostgreSQL session row is the serialization point used by answer acceptance and report
generation. A purge takes its FOR UPDATE lock, then removes the report, activity, interview,
and otherwise-unreferenced candidate in one transaction. No application content is logged.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import InterviewNotFound
from app.db.models import (
    ActivityEventRow,
    CandidateRow,
    InterviewReportRow,
    InterviewSessionRow,
    JobRow,
)


async def _delete_locked_interview(session: AsyncSession, row: InterviewSessionRow) -> None:
    """Remove one locked interview and its candidate if no other session references it."""
    candidate_id = row.candidate_id
    await session.execute(
        delete(ActivityEventRow).where(ActivityEventRow.interview_id == row.id)
    )
    await session.execute(
        delete(InterviewReportRow).where(InterviewReportRow.interview_id == row.id)
    )
    await session.delete(row)
    await session.flush()
    if candidate_id:
        await session.execute(
            delete(CandidateRow).where(
                CandidateRow.id == candidate_id,
                ~exists().where(InterviewSessionRow.candidate_id == candidate_id),
            )
        )


async def delete_interview_for_recruiter(
    sessions: async_sessionmaker, *, interview_id: str, recruiter_id: str
) -> None:
    """Delete only an interview owned by this recruiter; unknown/foreign IDs are identical."""
    async with sessions() as session, session.begin():
        row = await session.scalar(
            select(InterviewSessionRow)
            .join(JobRow, JobRow.id == InterviewSessionRow.job_id)
            .where(
                InterviewSessionRow.id == interview_id,
                JobRow.recruiter_id == recruiter_id,
            )
            .with_for_update(of=InterviewSessionRow)
        )
        if row is None:
            raise InterviewNotFound(interview_id)
        await _delete_locked_interview(session, row)


async def purge_expired_interviews(
    sessions: async_sessionmaker,
    *,
    now: datetime | None = None,
    retention_days: int = 90,
    batch_size: int = 100,
) -> int:
    """Purge at most one bounded batch; stale or locked rows are safely retried tomorrow.

    A stored report can be created after the last answer, so its creation time also extends
    retention. Recheck both timestamps after locking to avoid deleting a concurrent update.
    """
    if retention_days < 1 or not 1 <= batch_size <= 1000:
        raise ValueError("invalid retention sweep bounds")
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    async with sessions() as session:
        ids = list(
            await session.scalars(
                select(InterviewSessionRow.id)
                .outerjoin(
                    InterviewReportRow,
                    InterviewReportRow.interview_id == InterviewSessionRow.id,
                )
                .where(
                    InterviewSessionRow.last_activity_at < cutoff,
                    or_(
                        InterviewReportRow.created_at.is_(None),
                        InterviewReportRow.created_at < cutoff,
                    ),
                )
                .order_by(InterviewSessionRow.last_activity_at)
                .limit(batch_size)
            )
        )
    deleted = 0
    for interview_id in ids:
        async with sessions() as session, session.begin():
            row = await session.scalar(
                select(InterviewSessionRow)
                .where(InterviewSessionRow.id == interview_id)
                .with_for_update(skip_locked=True)
            )
            if row is None or row.last_activity_at >= cutoff:
                continue
            report_created = await session.scalar(
                select(InterviewReportRow.created_at).where(
                    InterviewReportRow.interview_id == interview_id
                )
            )
            if report_created is not None and report_created >= cutoff:
                continue
            await _delete_locked_interview(session, row)
            deleted += 1
    return deleted


async def purge_orphan_data(
    sessions: async_sessionmaker,
    *,
    now: datetime | None = None,
    retention_days: int = 90,
    batch_size: int = 100,
) -> tuple[int, int]:
    """Remove aged candidate/activity rows left by interrupted or legacy workflows.

    The application creates a fresh candidate ID immediately before starting an interview,
    so a candidate older than the retention window with no referring session is orphaned.
    Predicates are rechecked in each DELETE transaction.
    """
    if retention_days < 1 or not 1 <= batch_size <= 1000:
        raise ValueError("invalid retention sweep bounds")
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    async with sessions() as session, session.begin():
        candidate_ids = list(await session.scalars(
            select(CandidateRow.id)
            .where(
                CandidateRow.created_at < cutoff,
                ~exists().where(InterviewSessionRow.candidate_id == CandidateRow.id),
            )
            .limit(batch_size)
        ))
        activity_ids = list(await session.scalars(
            select(ActivityEventRow.id)
            .where(
                ActivityEventRow.created_at < cutoff,
                ~exists().where(InterviewSessionRow.id == ActivityEventRow.interview_id),
            )
            .limit(batch_size)
        ))
        candidate_count = 0
        activity_count = 0
        if candidate_ids:
            candidate_count = (await session.execute(
                delete(CandidateRow).where(
                    CandidateRow.id.in_(candidate_ids),
                    CandidateRow.created_at < cutoff,
                    ~exists().where(InterviewSessionRow.candidate_id == CandidateRow.id),
                )
            )).rowcount
        if activity_ids:
            activity_count = (await session.execute(
                delete(ActivityEventRow).where(
                    ActivityEventRow.id.in_(activity_ids),
                    ActivityEventRow.created_at < cutoff,
                    ~exists().where(InterviewSessionRow.id == ActivityEventRow.interview_id),
                )
            )).rowcount
    return candidate_count, activity_count
