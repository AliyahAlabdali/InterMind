"""Interview-session use case: drives the LangGraph interview loop over plain async calls.

Bridges the HTTP layer and :mod:`app.agents.interview_graph`, which owns the actual LangGraph
``StateGraph``/checkpointer. This service only resolves identifiers through repositories and
maps LangGraph state onto :class:`~app.domain.interview.InterviewState` - it holds no
interview or evaluation logic of its own.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app.agents.interview_graph import build_graph_state
from app.core.exceptions import InterviewAlreadyCompleted, InterviewStateUnavailable
from app.domain.candidate import Candidate
from app.domain.interview import InterviewState, InterviewStatus
from app.domain.interview_plan import InterviewPlan
from app.repositories.ports import (
    CandidateRepository,
    InterviewPlanRepository,
    InterviewSession,
    InterviewSessionRepository,
)

_REQUIRED_STATE_KEYS = ("job_id", "status", "asked_question_ids")


def _to_interview_state(interview_id: str, raw_state: Mapping[str, Any]) -> InterviewState:
    """Validate ``raw_state`` (a LangGraph checkpoint's ``values``) and map it to
    :class:`InterviewState`.

    Never assumes ``raw_state`` is a valid interview state: an empty mapping means no
    checkpoint was ever recorded for this thread id (e.g. the session repository and the
    graph checkpointer have gone out of sync); a non-empty one missing required keys, or
    holding a ``status`` that isn't a recognised :class:`InterviewStatus`, is treated the
    same way rather than silently defaulting.

    Raises:
        app.core.exceptions.InterviewStateUnavailable: ``raw_state`` is missing or does not
            look like a valid interview state.
    """
    if not raw_state:
        raise InterviewStateUnavailable(interview_id, "no checkpointed state found")

    missing = [key for key in _REQUIRED_STATE_KEYS if key not in raw_state]
    if missing:
        raise InterviewStateUnavailable(
            interview_id, f"checkpoint is missing required field(s): {missing}"
        )

    job_id = raw_state["job_id"]
    if not isinstance(job_id, str) or not job_id:
        raise InterviewStateUnavailable(interview_id, "checkpoint has an invalid job_id")

    try:
        status = InterviewStatus(raw_state["status"])
    except ValueError as exc:
        raise InterviewStateUnavailable(
            interview_id, f"checkpoint has an invalid status value: {raw_state['status']!r}"
        ) from exc

    asked_question_ids = list(raw_state["asked_question_ids"])
    return InterviewState(
        job_id=job_id,
        status=status,
        turn_index=len(asked_question_ids),
        history=list(raw_state.get("history", [])),
        current_question_id=raw_state.get("current_question_id"),
        current_question_text=raw_state.get("current_question_text"),
        asked_question_ids=asked_question_ids,
    )


def _thread_config(interview_id: str) -> dict:
    return {"configurable": {"thread_id": interview_id}}


class InterviewLockRegistry:
    """Per-interview-id asyncio locks, shared across requests for the process lifetime.

    Must be a single instance per process (see :func:`app.api.deps.get_interview_lock_registry`,
    cached on ``app.state``) - a fresh instance per request would defeat the point of locking,
    since two concurrent requests would each get their own empty registry and never actually
    serialize on the same interview id. Kept intentionally simple: no eviction, since this is
    in-memory, single-process, no-database scope for now (same as the checkpointer itself).
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def lock_for(self, interview_id: str) -> asyncio.Lock:
        return self._locks.setdefault(interview_id, asyncio.Lock())


@dataclass
class InterviewSessionService:
    graph: CompiledStateGraph
    plan_repo: InterviewPlanRepository
    session_repo: InterviewSessionRepository
    candidate_repo: CandidateRepository
    locks: InterviewLockRegistry = field(default_factory=InterviewLockRegistry)

    async def start(
        self, job_id: str, candidate_name: str = "Candidate", candidate_email: str = ""
    ) -> tuple[str, InterviewState]:
        """Start a new interview thread from the job's existing plan, for a named candidate.

        Creates a new :class:`~app.domain.candidate.Candidate` and associates it with the new
        :class:`~app.repositories.ports.InterviewSession` - see the recruiter-workflow
        architecture review: the recruiter must be able to tell which candidate completed
        which interview, so identity is captured at invitation time rather than left implicit.

        Raises:
            app.core.exceptions.InterviewPlanNotFound: no plan exists for ``job_id`` yet.
        """
        plan: InterviewPlan = await self.plan_repo.get(job_id)
        candidate = await self.candidate_repo.add(
            Candidate(name=candidate_name, email=candidate_email)
        )
        session = await self.session_repo.add(
            InterviewSession(job_id=job_id, candidate_id=candidate.id)
        )

        raw_state = await self.graph.ainvoke(
            build_graph_state(plan), config=_thread_config(session.id)
        )
        return session.id, _to_interview_state(session.id, raw_state)

    async def submit_answer(self, interview_id: str, answer: str) -> InterviewState:
        """Resume the interview thread with ``answer``.

        Serialized per ``interview_id`` via :class:`InterviewLockRegistry` so two duplicate or
        genuinely concurrent submissions for the same interview can't both observe
        "not completed" and race each other into ``graph.ainvoke`` - the second one always
        re-checks state (now advanced by the first) before acting, rather than corrupting the
        checkpoint or crashing on a stale interrupt.

        Raises:
            app.core.exceptions.InterviewNotFound: no interview with that id.
            app.core.exceptions.InterviewAlreadyCompleted: the interview already finished.
            app.core.exceptions.InterviewStateUnavailable: the checkpointed state is missing
                or invalid.
        """
        await self.session_repo.get(interview_id)

        async with self.locks.lock_for(interview_id):
            config = _thread_config(interview_id)

            snapshot = await self.graph.aget_state(config)
            current_state = _to_interview_state(interview_id, snapshot.values)
            if current_state.status == InterviewStatus.COMPLETED:
                raise InterviewAlreadyCompleted(interview_id)

            raw_state = await self.graph.ainvoke(Command(resume=answer), config=config)
            return _to_interview_state(interview_id, raw_state)

    async def get_state(self, interview_id: str) -> InterviewState:
        """Return the interview's current state without advancing it.

        Raises:
            app.core.exceptions.InterviewNotFound: no interview with that id.
            app.core.exceptions.InterviewStateUnavailable: the checkpointed state is missing
                or invalid.
        """
        await self.session_repo.get(interview_id)
        snapshot = await self.graph.aget_state(_thread_config(interview_id))
        return _to_interview_state(interview_id, snapshot.values)
