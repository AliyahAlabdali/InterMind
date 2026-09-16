"""LangGraph interview loop: select a question, ask it, evaluate the answer, repeat.

Owns the :class:`~langgraph.graph.state.StateGraph` wiring and its in-memory checkpointer.
Answer scoring itself lives behind :class:`app.services.answer_evaluation.AnswerEvaluationService`
(an :class:`~app.llm.ports.LLMClient` boundary), injected into the graph via
:func:`build_interview_graph` rather than hardcoded into a node - so the graph has no LLM logic
of its own. :mod:`app.services.interview_session` drives this graph and maps its state onto the
:class:`~app.domain.interview.InterviewState` domain model for everything outside this module.
"""

from __future__ import annotations

import hashlib
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from app.domain.evaluation import (
    DEFAULT_MAX_FOLLOW_UPS,
    EvaluationDecision,
    resolve_follow_up_decision,
)
from app.domain.interview_plan import InterviewPlan
from app.services.answer_evaluation import AnswerEvaluationService


class InterviewGraphState(TypedDict):
    job_id: str
    questions: list[dict]
    current_question_id: str | None
    current_question_text: str | None
    current_follow_up_id: str | None
    candidate_answer: str | None
    evaluation: str | None
    follow_up_question: str | None
    asked_question_ids: list[str]
    follow_up_count: int
    status: str
    history: list[dict]


def build_graph_state(interview_plan: InterviewPlan) -> InterviewGraphState:
    return {
        "job_id": interview_plan.job_id,
        "questions": [
            {
                "id": question.id,
                "text": question.text,
                "category": question.category.value,
                "target": question.target,
                "grounding": question.grounding,
            }
            for question in interview_plan.questions
        ],
        "current_question_id": None,
        "current_question_text": None,
        "current_follow_up_id": None,
        "candidate_answer": None,
        "evaluation": None,
        "follow_up_question": None,
        "asked_question_ids": [],
        "follow_up_count": 0,
        "status": "not_started",
        "history": [],
    }


def _follow_up_question_id(parent_question_id: str, index: int) -> str:
    """Stable id for the ``index``-th follow-up asked on ``parent_question_id``.

    Deterministic (not a fresh ``uuid4()``) for the same reason ``InterviewPlannerService.
    _question_id`` is: rebuilding/replaying the same interview state should reproduce the same
    follow-up id, not a new one each time. Distinct from the parent question's own id (never
    collides with a planned question id), so it can be safely appended to
    ``asked_question_ids`` alongside planned question ids without ever being mistaken for one -
    see ``select_question``, which only ever looks up ids from the plan's own question list.
    """
    key = f"{parent_question_id}|followup|{index}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _find_question(state: InterviewGraphState, question_id: str | None) -> dict:
    return next(q for q in state["questions"] if q["id"] == question_id)


def select_question(state: InterviewGraphState) -> dict:
    for question in state["questions"]:
        if question["id"] not in state["asked_question_ids"]:
            return {
                "current_question_id": question["id"],
                "current_question_text": question["text"],
                "current_follow_up_id": None,
                "asked_question_ids": state["asked_question_ids"]
                + [question["id"]],
                "status": "in_progress",
                "follow_up_count": 0,
            }

    return {
        "current_question_id": None,
        "current_question_text": None,
        "current_follow_up_id": None,
        "status": "completed",
    }


def ask_question(state: InterviewGraphState) -> dict:
    question = _find_question(state, state["current_question_id"])
    answer = interrupt(
        {
            "type": "question",
            "question_id": question["id"],
            "question": question["text"],
            "category": question["category"],
            "target": question["target"],
        }
    )

    return {
        "candidate_answer": answer,
    }


def _make_evaluate_answer(evaluator: AnswerEvaluationService):
    async def evaluate_answer(state: InterviewGraphState) -> dict:
        answer = state["candidate_answer"]
        # `question` is always the *root* planned question - grounding/category/target never
        # change for a follow-up (a follow-up still probes the same competency/technology/task,
        # see `resolve_follow_up_decision`'s docstring: this is about identity, not the
        # follow-up policy). `current_question_id` is deliberately never repointed to the
        # follow-up's own id (see `follow_up_question`'s docstring), so this lookup stays valid
        # for either turn.
        question = _find_question(state, state["current_question_id"])
        follow_up_id = state.get("current_follow_up_id")
        # But the turn *being recorded* (and evaluated - see the `evaluator.evaluate` call
        # below) is whichever was actually just answered: the root question on the first turn,
        # or the follow-up on a second one. Using the root's id/text unconditionally here (the
        # pre-fix bug) makes a follow-up's own answer show up in history under the original
        # question's id and text, as if the candidate had answered that instead, and makes the
        # evaluator judge the follow-up answer against the original question's wording instead
        # of the follow-up's own - see the module-level bug reports this fixes.
        turn_question_id = follow_up_id or question["id"]
        turn_question_text = state.get("current_question_text") or question["text"]

        if answer is None or not answer.strip():
            # A blank answer has no evidence to evaluate - always worth one clarifying ask,
            # but still bounded by the same cap as any other follow-up (see
            # `resolve_follow_up_decision`): a candidate who submits blank twice in a row must
            # not be asked a third time indefinitely.
            at_cap = state["follow_up_count"] >= DEFAULT_MAX_FOLLOW_UPS
            history_entry = {
                "question_id": turn_question_id,
                "question": turn_question_text,
                "answer": answer or "",
                "evaluation": None,
                "root_question_id": question["id"],
            }
            if at_cap:
                return {
                    "evaluation": EvaluationDecision.ADVANCE.value,
                    "follow_up_question": None,
                    "history": state["history"] + [history_entry],
                }
            follow_up_text = "Could you share an answer to the question?"
            return {
                "evaluation": EvaluationDecision.FOLLOW_UP.value,
                "follow_up_question": follow_up_text,
                # `follow_up_question` (the graph node) interrupts immediately without
                # returning an update of its own - see its docstring - so the follow-up
                # phrasing must already be in `current_question_text` by the time this node
                # completes, or the candidate would see the *original* question text again
                # and appear to need two submissions to move past one follow-up.
                "current_question_text": follow_up_text,
                "history": state["history"] + [history_entry],
            }

        raw_result = await evaluator.evaluate(
            # The literal question text is whatever was actually asked for *this* turn - the
            # follow-up's own phrasing when this is a follow-up answer, not the root question's
            # text (the previous bug: the evaluator judged a follow-up answer against the
            # original question's wording, which can be semantically wrong - see the module-
            # level bug report this fixes). category/target/grounding stay root-derived: a
            # follow-up doesn't have its own category/target, it's still probing the same one.
            question_text=turn_question_text,
            category=question["category"],
            target=question["target"],
            grounding=question.get("grounding"),
            answer=answer,
        )
        # The LLM's own `decision` is its best single-shot guess, but the system - not the
        # model - has the final say on whether to advance or follow up, deterministically
        # re-derived from the evaluation's own evidence signal (score/weaknesses/follow-up
        # question) - see `resolve_follow_up_decision`'s docstring for why `decision` alone
        # proved unreliable in real end-to-end testing.
        result = resolve_follow_up_decision(
            raw_result, follow_ups_used=state["follow_up_count"]
        )

        update: dict = {
            "evaluation": result.decision.value,
            "follow_up_question": result.follow_up_question,
            "history": state["history"]
            + [
                {
                    "question_id": turn_question_id,
                    "question": turn_question_text,
                    "answer": answer,
                    "evaluation": result.model_dump(mode="json"),
                    "root_question_id": question["id"],
                }
            ],
        }
        if result.decision == EvaluationDecision.FOLLOW_UP and result.follow_up_question:
            # Same reasoning as the blank-answer branch above: set it here, before the
            # `follow_up_question` node interrupts, not inside that node's own (never-reached
            # before resume) return value. When the graph instead forces an advance despite a
            # follow_up decision (the one-follow-up cap - see `resolve_follow_up_decision`),
            # `select_question` overwrites this with the next question's text before any
            # interrupt is hit, so setting it speculatively here is harmless in that case.
            update["current_question_text"] = result.follow_up_question
        return update

    return evaluate_answer


def decide_after_evaluation(state: InterviewGraphState) -> str:
    """Route purely on the already-resolved decision - see `resolve_follow_up_decision`,
    which is where the follow-up cap and evidence-based policy are actually applied (in
    `evaluate_answer`), not here. Keeping a single source of truth for that policy avoids two
    places silently disagreeing on when a follow-up is warranted."""
    if state["evaluation"] == EvaluationDecision.FOLLOW_UP.value:
        return "follow_up"
    return "next_question"


def follow_up_question(state: InterviewGraphState) -> dict:
    """Ask the follow-up and wait for the candidate's answer to it.

    `state["current_question_text"]` must already equal `follow_up_text` by the time this
    node runs (set by `evaluate_answer`, not here) - this node's own `return` never executes
    until *after* the interrupt is resumed, so anything it returned couldn't affect what the
    candidate is shown for this follow-up in the meantime.

    The follow-up gets its own stable, deterministic id (`_follow_up_question_id`), recorded
    in `asked_question_ids` and `current_follow_up_id` exactly as a planned question is
    recorded by `select_question` - so a follow-up is a first-class, auditable interview turn,
    not an untracked side effect of a normal question. `evaluate_answer` uses
    `current_follow_up_id` (not the root question's id) as that turn's own `history[*].
    question_id`/`question` once it's answered - see its docstring for why using the root id
    there was the bug this fixes.

    `current_question_id` itself deliberately stays as the parent question's id throughout (a
    follow-up is still "about" that same planned question/target, not a new one) - existing
    consumers (the candidate API's `current_question_id`, `_find_question` in this module, the
    report's per-question grouping via `root_question_id`) key off it and must keep working
    unchanged.
    """
    follow_up_text = state.get("follow_up_question") or (
        "Can you explain that in more detail and give a specific example?"
    )
    follow_up_id = _follow_up_question_id(state["current_question_id"], state["follow_up_count"])
    follow_up = interrupt(
        {
            "type": "follow_up",
            "question_id": state["current_question_id"],
            "follow_up_id": follow_up_id,
            "question": follow_up_text,
        }
    )

    return {
        "candidate_answer": follow_up,
        "follow_up_count": state["follow_up_count"] + 1,
        "current_follow_up_id": follow_up_id,
        "asked_question_ids": state["asked_question_ids"] + [follow_up_id],
    }


def decide_next_question(state: InterviewGraphState) -> str:
    """Route based on whether ``select_question`` actually found another question.

    Checking ``current_question_id is not None`` (rather than comparing
    ``len(asked_question_ids)`` to ``len(questions)``) matters because ``select_question``
    appends to ``asked_question_ids`` the moment it *selects* a question, before it has been
    asked - comparing lengths would treat the just-selected last question as already asked
    and skip straight to ``finish`` without ever asking it.
    """
    if state["current_question_id"] is not None:
        return "next_question"

    return "finish"


def finish(state: InterviewGraphState) -> dict:
    return {
        "status": "completed",
        "current_question_id": None,
        "current_question_text": None,
    }


def build_interview_graph(evaluator: AnswerEvaluationService) -> CompiledStateGraph:
    """Compile the interview graph with ``evaluator`` bound into its evaluation node.

    Each call returns a fresh graph with its own :class:`InMemorySaver` checkpointer, so
    callers (see :func:`app.api.deps.get_interview_graph`) must build it once and reuse the
    same instance for the process lifetime - a new instance means a new, empty checkpoint
    store, and every existing ``thread_id`` would appear to have no state.
    """
    builder = StateGraph(InterviewGraphState)

    builder.add_node("select_question", select_question)
    builder.add_node("ask_question", ask_question)
    builder.add_node("evaluate_answer", _make_evaluate_answer(evaluator))
    builder.add_node("follow_up_question", follow_up_question)
    builder.add_node("finish", finish)

    builder.add_edge(START, "select_question")

    builder.add_conditional_edges(
        "select_question",
        decide_next_question,
        {
            "next_question": "ask_question",
            "finish": "finish",
        },
    )

    builder.add_edge("ask_question", "evaluate_answer")

    builder.add_conditional_edges(
        "evaluate_answer",
        decide_after_evaluation,
        {
            "next_question": "select_question",
            "follow_up": "follow_up_question",
        },
    )

    builder.add_edge("follow_up_question", "evaluate_answer")

    builder.add_edge("finish", END)

    return builder.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    import asyncio

    from app.domain.interview_plan import (
        InterviewPlan,
        InterviewQuestion,
        QuestionCategory,
    )
    from app.domain.occupation import OccupationMatch
    from app.llm.fake_client import FakeLLMClient

    async def _demo() -> None:
        graph = build_interview_graph(AnswerEvaluationService(llm=FakeLLMClient()))

        test_plan = InterviewPlan(
            job_id="job_123",
            occupation_match=OccupationMatch(
                onet_soc_code="15-1252.00",
                title="Software Developers",
                score=1.0,
            ),
            questions=[
                InterviewQuestion(
                    id="q1",
                    category=QuestionCategory.COMPETENCY,
                    text="What is overfitting?",
                    target="Machine Learning",
                    grounding="JobSpec: Machine Learning",
                ),
                InterviewQuestion(
                    id="q2",
                    category=QuestionCategory.TECHNOLOGY,
                    text="How do you evaluate an ML model?",
                    target="Machine Learning",
                    grounding="O*NET: Machine Learning",
                ),
                InterviewQuestion(
                    id="q3",
                    category=QuestionCategory.TASK,
                    text="Tell me about an AI project you built.",
                    target="AI project development",
                    grounding="O*NET: Software Developers",
                ),
            ],
        )

        config = {"configurable": {"thread_id": test_plan.job_id}}

        print("Starting interview...")
        result = await graph.ainvoke(build_graph_state(test_plan), config=config)
        print("\nFIRST RESULT:")
        print(result)

        print("\nSubmitting answer...")
        from langgraph.types import Command

        result = await graph.ainvoke(
            Command(
                resume=(
                    "Overfitting happens when a model learns the training data too closely "
                    "and performs poorly on unseen data."
                )
            ),
            config=config,
        )
        print("\nSECOND RESULT:")
        print(result)

    asyncio.run(_demo())
