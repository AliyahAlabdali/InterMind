"""Interview state.

Originally an intentionally minimal, behaviour-free skeleton (Milestone 1) so a later
milestone could wrap the interview lifecycle in a stateful orchestrator without restructuring
the domain. Milestone 4 does that wrapping: :mod:`app.agents.interview_graph` owns the actual
LangGraph state/transitions, and :mod:`app.services.interview_session` maps its state onto this
model - the API layer and callers outside the graph only ever see :class:`InterviewState`.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class InterviewStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class InterviewState(BaseModel):
    """Serialisable state for a single interview session.

    **Identity contract (root target vs. current turn vs. follow-up)** - reviewed and kept
    as-is (Copilot review, cross-target/JD-grounding pass): there are three distinct notions
    of "which question" at any point in an interview, and only two of them are exposed here:

    - The *root target's identity* - ``current_question_id``. Stable across an entire target's
      lifetime, including any follow-up on it: it never changes to the follow-up's own id, even
      while the follow-up is what's actually being shown/answered. This is deliberate, not an
      oversight - see ``app.agents.interview_graph.follow_up_question``'s docstring. It exists
      so callers (this API, the report's per-target grouping) always have one stable id to key
      a target's *outcome* on, regardless of how many turns it took to reach it.
    - The *actual current turn's content* - ``current_question_text``. This *does* change to
      the follow-up's own phrasing once one is asked, even though ``current_question_id``
      doesn't move - so a caller rendering "the current question" must always use
      ``current_question_text``, never re-derive display text from ``current_question_id``.
    - The *follow-up's own identity* - never exposed as ``current_question_id``. It exists only
      inside ``history[*].question_id`` and ``asked_question_ids`` (see
      ``app.agents.interview_graph._follow_up_question_id``), each entry keeping a
      ``root_question_id`` pointing back at the target it belongs to.

    This contract was deliberately kept rather than changed: nothing in this API needs a
    per-turn id (``POST /interviews/{id}/answers`` takes no question id at all - the graph
    always knows what it's currently waiting on), and introducing one here would only add a
    field every existing caller (candidate frontend routing, report attribution) would need to
    learn to ignore. See ``tests/unit/test_interview_session_service.py::
    test_current_question_id_contract_during_a_follow_up`` for a regression test pinning this
    contract down directly.
    """

    job_id: str
    status: InterviewStatus = InterviewStatus.NOT_STARTED
    turn_index: int = 0
    history: list[dict] = Field(default_factory=list)
    current_question_id: str | None = None
    current_question_text: str | None = None
    asked_question_ids: list[str] = Field(default_factory=list)