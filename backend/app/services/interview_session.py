"""Interview-session use case: drives the LangGraph interview loop over plain async calls.

Bridges the HTTP layer and :mod:`app.agents.interview_graph`, which owns the actual LangGraph
``StateGraph``/checkpointer. This service only resolves identifiers through repositories and
maps LangGraph state onto :class:`~app.domain.interview.InterviewState` - it holds no
interview or evaluation logic of its own.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app.agents.interview_graph import build_graph_state
from app.core.exceptions import (
    InterviewAlreadyCompleted,
    InterviewStateUnavailable,
    StaleInterviewTurn,
)
from app.domain.candidate import Candidate
from app.domain.interview import InterviewState, InterviewStatus
from app.domain.interview_plan import InterviewPlan
from app.repositories.ports import (
    CandidateRepository,
    InterviewPlanRepository,
    InterviewSession,
    InterviewSessionRepository,
)

logger = logging.getLogger(__name__)

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
    since two concurrent requests would each get their own empty registry. PostgreSQL also
    locks each session row during turn acceptance and report generation.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        # The configured engine uses SQLAlchemy's default 5+10 connection pool. A report
        # or Speech operation holds its session row while another repository reads data.
        # Leave room for those reads instead of letting lock holders fill the entire pool.
        self.transactions = asyncio.Semaphore(4)

    def lock_for(self, interview_id: str) -> asyncio.Lock:
        return self._locks.setdefault(interview_id, asyncio.Lock())


@dataclass
class InterviewSessionService:
    graph: CompiledStateGraph
    plan_repo: InterviewPlanRepository
    session_repo: InterviewSessionRepository
    candidate_repo: CandidateRepository
    locks: InterviewLockRegistry = field(default_factory=InterviewLockRegistry)

    async def _snapshot(self, interview_id: str) -> dict:
        snapshot = await self.graph.aget_state(_thread_config(interview_id))
        state = _to_interview_state(interview_id, snapshot.values)
        pending = snapshot.next[0] if len(snapshot.next) == 1 else None
        if state.status != InterviewStatus.COMPLETED and pending not in (
            "ask_question", "follow_up_question"
        ):
            raise InterviewStateUnavailable(interview_id, "no answerable pending node")
        return {
            "version": 1,
            "values": dict(snapshot.values),
            "pending_node": pending,
            "turn_id": uuid4().hex if pending else None,
        }

    @staticmethod
    def _saved_state(session: InterviewSession) -> InterviewState:
        saved = session.runtime_snapshot
        if not isinstance(saved, dict) or saved.get("version") != 1:
            raise InterviewStateUnavailable(session.id, "no durable runtime snapshot")
        values = saved.get("values")
        if not isinstance(values, dict):
            raise InterviewStateUnavailable(session.id, "invalid durable runtime values")
        state = _to_interview_state(session.id, values)
        if state.job_id != session.job_id:
            raise InterviewStateUnavailable(session.id, "snapshot job mismatch")
        if state.status == InterviewStatus.IN_PROGRESS:
            turn = saved.get("turn_id")
            if (saved.get("pending_node") not in ("ask_question", "follow_up_question")
                    or not isinstance(turn, str) or len(turn) != 32
                    or not state.current_question_id or not state.current_question_text):
                raise InterviewStateUnavailable(session.id, "no durable answerable turn")
            state.current_turn_id = turn
        elif state.status != InterviewStatus.COMPLETED or saved.get("pending_node") is not None:
            raise InterviewStateUnavailable(session.id, "invalid durable lifecycle state")
        return state

    async def _restore(self, session: InterviewSession) -> None:
        """Recreate only the pending interrupt, without repeating accepted evaluation/LLM work.

        Each invocation starts from the committed snapshot, even after a previous invocation
        failed part-way through. Failed attempts therefore cannot silently advance a turn.
        """
        saved = session.runtime_snapshot
        config = _thread_config(session.id)
        await self.graph.checkpointer.adelete_thread(session.id)
        previous_node = {
            "ask_question": "select_target",
            "follow_up_question": "evaluate_answer",
        }[saved["pending_node"]]
        await self.graph.aupdate_state(config, saved["values"], as_node=previous_node)
        await self.graph.ainvoke(None, config=config)

    async def start(
        self, job_id: str, candidate_name: str = "Candidate", candidate_email: str = ""
    ) -> tuple[str, InterviewState]:
        plan: InterviewPlan = await self.plan_repo.get(job_id)
        candidate = Candidate(name=candidate_name, email=candidate_email)
        session = InterviewSession(job_id=job_id, candidate_id=candidate.id)
        started_at = time.perf_counter()
        try:
            await self.graph.ainvoke(build_graph_state(plan), config=_thread_config(session.id))
            session.runtime_snapshot = await self._snapshot(session.id)
            state = self._saved_state(session)
            # Do not publish an invitation until its first question is usable.
            await self.candidate_repo.add(candidate)
            await self.session_repo.add(session)
        finally:
            await self.graph.checkpointer.adelete_thread(session.id)
        logger.info(
            "interview_timing phase=total_turn seconds=%.4f interview_id=%s turn=start",
            time.perf_counter() - started_at, session.id,
        )
        return session.id, state

    async def submit_answer(
        self, interview_id: str, answer: str, turn_id: str
    ) -> InterviewState:
        """Consume exactly the observed turn and commit evidence before acknowledging it.

        The process lock protects the graph cache; the PostgreSQL row lock serializes the
        durable compare/advance/commit across processes. A stale or exact duplicate is rejected
        (412), never applied to the next question. Completion remains 409.
        """
        async with self.locks.lock_for(interview_id), self.locks.transactions:
            async with self.session_repo.locked(interview_id) as session:
                current = self._saved_state(session)
                if current.status == InterviewStatus.COMPLETED:
                    raise InterviewAlreadyCompleted(interview_id)
                if current.current_turn_id != turn_id:
                    raise StaleInterviewTurn()
                started_at = time.perf_counter()
                try:
                    await self._restore(session)
                    await self.graph.ainvoke(
                        Command(resume=answer), config=_thread_config(interview_id)
                    )
                    session.runtime_snapshot = await self._snapshot(interview_id)
                    state = self._saved_state(session)
                finally:
                    await self.graph.checkpointer.adelete_thread(interview_id)
                logger.info(
                    "interview_timing phase=total_turn seconds=%.4f interview_id=%s turn=answer",
                    time.perf_counter() - started_at, interview_id,
                )
            # Exiting the repository transaction successfully is part of accepting evidence.
            return state

    async def get_state(self, interview_id: str) -> InterviewState:
        """Read the last committed state; never expose a graph's partial/failed transition."""
        return self._saved_state(await self.session_repo.get(interview_id))
