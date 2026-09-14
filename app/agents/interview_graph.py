"""LangGraph interview loop: select a question, ask it, evaluate the answer, repeat.

Owns the :class:`~langgraph.graph.state.StateGraph` wiring and its in-memory checkpointer.
Answer scoring itself lives behind :class:`app.services.answer_evaluation.AnswerEvaluationService`
(an :class:`~app.llm.ports.LLMClient` boundary), injected into the graph via
:func:`build_interview_graph` rather than hardcoded into a node - so the graph has no LLM logic
of its own. :mod:`app.services.interview_session` drives this graph and maps its state onto the
:class:`~app.domain.interview.InterviewState` domain model for everything outside this module.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from app.domain.evaluation import EvaluationDecision
from app.domain.interview_plan import InterviewPlan
from app.services.answer_evaluation import AnswerEvaluationService


class InterviewGraphState(TypedDict):
    job_id: str
    questions: list[dict]
    current_question_id: str | None
    current_question_text: str | None
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
        "candidate_answer": None,
        "evaluation": None,
        "follow_up_question": None,
        "asked_question_ids": [],
        "follow_up_count": 0,
        "status": "not_started",
        "history": [],
    }


def _find_question(state: InterviewGraphState, question_id: str | None) -> dict:
    return next(q for q in state["questions"] if q["id"] == question_id)


def select_question(state: InterviewGraphState) -> dict:
    for question in state["questions"]:
        if question["id"] not in state["asked_question_ids"]:
            return {
                "current_question_id": question["id"],
                "current_question_text": question["text"],
                "asked_question_ids": state["asked_question_ids"]
                + [question["id"]],
                "status": "in_progress",
                "follow_up_count": 0,
            }

    return {
        "current_question_id": None,
        "current_question_text": None,
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
        question = _find_question(state, state["current_question_id"])

        if answer is None or not answer.strip():
            return {
                "evaluation": EvaluationDecision.FOLLOW_UP.value,
                "follow_up_question": "Could you share an answer to the question?",
                "history": state["history"]
                + [
                    {
                        "question_id": question["id"],
                        "question": question["text"],
                        "answer": answer or "",
                        "evaluation": None,
                    }
                ],
            }

        result = await evaluator.evaluate(
            question_text=question["text"],
            category=question["category"],
            target=question["target"],
            grounding=question.get("grounding"),
            answer=answer,
        )

        return {
            "evaluation": result.decision.value,
            "follow_up_question": result.follow_up_question,
            "history": state["history"]
            + [
                {
                    "question_id": question["id"],
                    "question": question["text"],
                    "answer": answer,
                    "evaluation": result.model_dump(mode="json"),
                }
            ],
        }

    return evaluate_answer


def decide_after_evaluation(state: InterviewGraphState) -> str:
    if state["evaluation"] == EvaluationDecision.ADVANCE.value:
        return "next_question"

    if state["follow_up_count"] == 0:
        return "follow_up"

    return "next_question"


def follow_up_question(state: InterviewGraphState) -> dict:
    follow_up_text = state.get("follow_up_question") or (
        "Can you explain that in more detail and give a specific example?"
    )
    follow_up = interrupt(
        {
            "type": "follow_up",
            "question_id": state["current_question_id"],
            "question": follow_up_text,
        }
    )

    return {
        "candidate_answer": follow_up,
        "follow_up_count": state["follow_up_count"] + 1,
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
