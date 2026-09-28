"""The persistent schema.

Everything a recruiter owns lives here, because an account that vanishes on restart is not an
account. The application's own types stay Pydantic domain models (``app.domain``); these ORM
classes are storage only, and nothing outside ``app.repositories.sql`` should import them.

Ownership
---------
``jobs.recruiter_id`` is the **single authoritative ownership edge**. Everything else derives
from it by relationship::

    Recruiter ─owns→ Job ─┬→ InterviewPlan
                          ├→ InterviewSession ─┬→ InterviewReport
                          │                    └→ (candidate answers, via LangGraph)
                          └→ ActivityEvent

No other table carries ``recruiter_id``. Denormalising it into five tables would give five
places for ownership to drift apart, and every query that needs it can reach a job in one join.

Deletion
--------
``jobs.recruiter_id`` is ``RESTRICT``, deliberately: a recruiter cannot be deleted while they
own jobs, so no accidental ORM cascade can erase candidate interview history as a side effect of
removing an account. Within a job's own subtree the cascades are ``CASCADE``, since a plan, a
session, a report and an activity row have no meaning without their job. There is no deletion
feature in the product yet; account-deletion semantics are future product/legal work.

JSON columns
------------
Document-shaped values (a job spec, an interview plan, a report) are stored as JSON rather than
shredded into columns. They are read and written whole, they are owned by the Pydantic models
that define them, and normalising them would couple the schema to evaluation and report
internals that are deliberately frozen. ``JSONB`` on PostgreSQL, portable ``JSON`` elsewhere so
the suite can run without a database server.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

#: JSONB where it exists, plain JSON elsewhere.
JsonDoc = JSON().with_variant(JSONB(), "postgresql")

#: Ids are 32-character uuid4 hex strings throughout the domain (``uuid4().hex``).
IdStr = String(32)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class RecruiterRow(Base):
    """A recruiter account. Email plus password hash; nothing else is needed yet."""

    __tablename__ = "recruiters"

    id: Mapped[str] = mapped_column(IdStr, primary_key=True)
    #: Stored already normalised (trimmed, lower-cased) - see
    #: ``app.domain.recruiter.normalize_email``. The unique index is on this column, so
    #: "A@b.com" and "a@b.com" cannot both exist, and the database is what enforces it rather
    #: than a check-then-insert that two concurrent signups could both pass.
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    #: scrypt, encoded with its own parameters - see ``app.core.security``. Never a plaintext
    #: password, and never returned by the API.
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class JobRow(Base):
    """An analysed job. The ownership root."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(IdStr, primary_key=True)
    #: RESTRICT: see the module docstring. Indexed because every recruiter-scoped query
    #: filters on it.
    recruiter_id: Mapped[str] = mapped_column(
        IdStr, ForeignKey("recruiters.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    job_description: Mapped[str] = mapped_column(Text, nullable=False)
    job_spec: Mapped[dict] = mapped_column(JsonDoc, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class InterviewPlanRow(Base):
    """At most one plan per job - re-planning overwrites it, so the job id is the key."""

    __tablename__ = "interview_plans"

    job_id: Mapped[str] = mapped_column(
        IdStr, ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    plan: Mapped[dict] = mapped_column(JsonDoc, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class CandidateRow(Base):
    """An invited candidate. Not recruiter-scoped directly; reached through their session."""

    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(IdStr, primary_key=True)
    name: Mapped[str] = mapped_column(String(320), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class InterviewSessionRow(Base):
    """One candidate's interview. ``access_token`` is the candidate's own credential.

    The interview's *progress* still lives in the LangGraph checkpointer, which is unchanged and
    remains in-memory: this row is the durable record that the interview exists, which job it
    belongs to, and who may open it.
    """

    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(IdStr, primary_key=True)
    job_id: Mapped[str] = mapped_column(
        IdStr, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_id: Mapped[str] = mapped_column(IdStr, nullable=False, default="")
    #: Opaque per-interview candidate credential. Indexed only by id; never looked up by token.
    access_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class InterviewReportRow(Base):
    """At most one report per interview - generated once, then returned unchanged."""

    __tablename__ = "interview_reports"

    interview_id: Mapped[str] = mapped_column(
        IdStr, ForeignKey("interview_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    report: Mapped[dict] = mapped_column(JsonDoc, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class ActivityEventRow(Base):
    """Append-only feed of what the interview has been doing, for the recruiter workspace."""

    __tablename__ = "activity_events"

    id: Mapped[str] = mapped_column(IdStr, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    interview_id: Mapped[str] = mapped_column(IdStr, nullable=False)
    #: Carries the ownership edge: the feed is scoped by joining to the recruiter's jobs.
    job_id: Mapped[str] = mapped_column(
        IdStr, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    candidate_name: Mapped[str] = mapped_column(String(320), nullable=False)
    target: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        # The feed is always "this recruiter's jobs, newest first".
        Index("ix_activity_events_job_created", "job_id", "created_at"),
    )
