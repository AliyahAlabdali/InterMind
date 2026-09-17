"""LangGraph interview loop: adaptively select a target, generate its question, ask it,
evaluate the answer, and decide what happens next - repeat until every category is either out
of budget or out of targets.

**Architecture note (the fix this module embodies):** the interview used to walk a fixed list
of already-phrased ``InterviewQuestion``s built once at plan time - genuinely adaptive only in
its follow-ups, never in *which* main question came next or how many there would be. That list
is gone. :class:`~app.domain.interview_plan.InterviewPlan` now only supplies
``coverage_targets`` (what *could* be assessed, see that module). Each time the interview needs
a new main question, this graph (1) asks :mod:`app.services.target_selection` which
not-yet-assessed target to cover next, given everything asked/answered so far, then (2) calls
:class:`~app.services.question_generation.QuestionGenerationService` to phrase a question for
*that* target *now*, with the interview's own history available to it - never a lookup into a
precomputed list. The number of questions a candidate ends up answering is therefore an outcome
of the interview, not a property of the plan.

Answer scoring itself still lives behind
:class:`app.services.answer_evaluation.AnswerEvaluationService` (an
:class:`~app.llm.ports.LLMClient` boundary), injected into the graph via
:func:`build_interview_graph` rather than hardcoded into a node - so the graph has no LLM logic
of its own beyond calling out to the two injected services. :mod:`app.services.interview_session`
drives this graph and maps its state onto the :class:`~app.domain.interview.InterviewState`
domain model for everything outside this module.
"""

from __future__ import annotations

import hashlib
import logging
import time
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
from app.services.cross_target_evidence import resolve_cross_target_evidence
from app.services.question_generation import QuestionGenerationService
from app.services.target_selection import DEFAULT_POLICY, TargetSelectionPolicy, select_next_target

logger = logging.getLogger(__name__)


class InterviewGraphState(TypedDict):
    job_id: str
    role_title: str
    seniority: str
    onet_context: str
    coverage_targets: list[dict]
    assessed_target_ids: list[str]
    target_hints: dict[str, dict]
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
        "role_title": interview_plan.role_title,
        "seniority": interview_plan.seniority.value,
        "onet_context": interview_plan.onet_context,
        "coverage_targets": [
            {
                "id": target.id,
                "target": target.target,
                "category": target.category.value,
                "requirement_level": target.requirement_level.value,
                "priority": target.priority,
                "grounding": target.grounding,
            }
            for target in interview_plan.coverage_targets
        ],
        "assessed_target_ids": [],
        "target_hints": {},
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

    Deterministic (not a fresh ``uuid4()``) for the same reason a coverage target's own id is
    (see ``app.services.target_identity``): rebuilding/replaying the same interview state
    should reproduce the same follow-up id, not a new one each time. Distinct from any target's
    own id (never collides with one), so it can be safely appended to ``asked_question_ids``
    alongside target ids without ever being mistaken for one - see ``select_target``, which
    only ever looks up ids from ``coverage_targets``.
    """
    key = f"{parent_question_id}|followup|{index}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _find_target(state: InterviewGraphState, target_id: str | None) -> dict:
    return next(t for t in state["coverage_targets"] if t["id"] == target_id)


def _history_context(history: list[dict]) -> str:
    """Render the interview so far as plain text for the runtime question generator.

    Deliberately excludes the evaluation itself (score/decision/strengths/weaknesses) - the
    question generator only needs to know what's already been asked and said, not how it was
    scored, and this keeps that scoring signal from ever leaking into question *phrasing*.
    """
    lines: list[str] = []
    for turn in history:
        question = turn.get("question")
        if not question:
            continue
        lines.append(f"PREVIOUS_Q: {question}")
        lines.append(f"PREVIOUS_A: {turn.get('answer') or ''}")
    return "\n".join(lines)


def _jd_context(state: InterviewGraphState, target: dict) -> str:
    """The job description's own requirements, relevant to phrasing ``target``'s question.

    Built entirely from data already on the plan/state (``role_title``/``seniority`` copied
    from the JobSpec at plan-build time, ``coverage_targets`` derived from the JD's own
    competencies/technologies/tasks - see ``app.services.interview_planner``) - never from
    O*NET, which stays supplementary context passed separately (``onet_context`` - see
    ``_make_select_target``). This is the fix for runtime question generation previously
    receiving only the bare target/role/O*NET/history with no JD grounding of its own: the JD
    is the source of truth for what this interview evaluates, so the generator should see that
    the same way a human interviewer would - what else the role requires, its seniority, and
    where this specific target sits (required or preferred, and why it's in the plan at all).
    """
    lines = [f"ROLE_TITLE: {state['role_title']}"]
    if state.get("seniority") and state["seniority"] != "unknown":
        lines.append(f"SENIORITY: {state['seniority']}")

    # Production incident: a real LLM generated questions for `COMPETENCIES`/
    # `RESPONSIBILITIES` entries listed below instead of the actual requested target - it read
    # this background list as a second, competing set of targets. The list-like formatting
    # below (comma/bullet lists, similar in shape to the real target-request lines) is kept -
    # removing the detail would make phrasing worse, not safer (see the module docstring's
    # "JD is the source of truth" principle) - but this note makes the boundary explicit right
    # where the confusion happened, not just once, far away, in the system prompt.
    lines.append(
        "NOTE: everything below in this JD_CONTEXT block (COMPETENCIES/REQUIRED_TECHNOLOGIES/"
        "PREFERRED_TECHNOLOGIES/RESPONSIBILITIES) is background about the role as a whole - "
        "it is NOT a list of additional targets. The only target for this question is the one "
        "requested above, before JD_CONTEXT."
    )

    targets = state["coverage_targets"]
    competencies = [t["target"] for t in targets if t["category"] == "competency"]
    required_tech = [
        t["target"]
        for t in targets
        if t["category"] == "technology" and t["requirement_level"] == "required"
    ]
    preferred_tech = [
        t["target"]
        for t in targets
        if t["category"] == "technology" and t["requirement_level"] == "preferred"
    ]
    responsibilities = [t["target"] for t in targets if t["category"] == "task"]

    if competencies:
        lines.append("COMPETENCIES: " + ", ".join(competencies))
    if required_tech:
        lines.append("REQUIRED_TECHNOLOGIES: " + ", ".join(required_tech))
    if preferred_tech:
        lines.append("PREFERRED_TECHNOLOGIES: " + ", ".join(preferred_tech))
    if responsibilities:
        lines.append("RESPONSIBILITIES:")
        lines.extend(f"- {r}" for r in responsibilities)

    lines.append(f"CURRENT_TARGET_REQUIREMENT_LEVEL: {target['requirement_level']}")
    if target.get("grounding"):
        lines.append(f"CURRENT_TARGET_GROUNDING: {target['grounding']}")

    hint = state.get("target_hints", {}).get(target["id"])
    if hint:
        # A prior, non-conclusive signal about this exact target - discovered incidentally
        # while a different question was being asked (see
        # app.services.cross_target_evidence). Never conclusive enough to have resolved the
        # target on its own, but worth the generator knowing about so it can ask a more
        # pointed, less redundant question rather than starting from nothing.
        lines.append(
            f"PRIOR_MENTION: The candidate briefly touched on {target['target']} earlier "
            f"({hint['evidence_type']}): \"{hint['note']}\""
        )

    return "\n".join(lines)


def _make_select_target(question_service: QuestionGenerationService, policy: TargetSelectionPolicy):
    async def select_target(state: InterviewGraphState) -> dict:
        # Latency instrumentation (adaptive-runtime review, item 6): target selection is a
        # pure, deterministic function over already-in-memory state - measured separately from
        # question generation (the LLM call) precisely to confirm it's negligible, rather than
        # assumed. See `app.services.interview_session` for the total-turn measurement this
        # composes into, and `app.llm.openai_client` for the LLM call's own duration.
        selection_started_at = time.perf_counter()
        target = select_next_target(
            state["coverage_targets"], state["assessed_target_ids"], policy
        )
        logger.info(
            "interview_timing phase=target_selection seconds=%.4f selected_target=%s",
            time.perf_counter() - selection_started_at,
            target["id"] if target else None,
        )
        if target is None:
            return {
                "current_question_id": None,
                "current_question_text": None,
                "current_follow_up_id": None,
                "status": "completed",
            }

        # The first question of the interview has no history to draw on yet (`_history_context`
        # of an empty list is `""`) - every later one does, since by construction this node only
        # runs again after a previous target has fully resolved (see `evaluate_answer`'s
        # `assessed_target_ids` bookkeeping) and its turn(s) are already in `state["history"]`.
        generation_started_at = time.perf_counter()
        generated = await question_service.generate(
            role_title=state["role_title"],
            targets=[(target["category"], target["target"])],
            jd_context=_jd_context(state, target),
            onet_context=state.get("onet_context", ""),
            history_context=_history_context(state["history"]),
        )
        logger.info(
            "interview_timing phase=question_generation seconds=%.4f target=%s",
            time.perf_counter() - generation_started_at,
            target["id"],
        )
        text = generated.questions[0].text

        return {
            "current_question_id": target["id"],
            "current_question_text": text,
            "current_follow_up_id": None,
            "asked_question_ids": state["asked_question_ids"] + [target["id"]],
            "status": "in_progress",
            "follow_up_count": 0,
        }

    return select_target


def ask_question(state: InterviewGraphState) -> dict:
    target = _find_target(state, state["current_question_id"])
    answer = interrupt(
        {
            "type": "question",
            "question_id": target["id"],
            "question": state["current_question_text"],
            "category": target["category"],
            "target": target["target"],
        }
    )

    return {
        "candidate_answer": answer,
    }


def _make_evaluate_answer(evaluator: AnswerEvaluationService):
    async def evaluate_answer(state: InterviewGraphState) -> dict:
        answer = state["candidate_answer"]
        # `target` is always the *root* coverage target - category/grounding never change for a
        # follow-up (a follow-up still probes the same competency/technology/task). `current_
        # question_id` is deliberately never repointed to the follow-up's own id (see
        # `follow_up_question`'s docstring), so this lookup stays valid for either turn.
        target = _find_target(state, state["current_question_id"])
        follow_up_id = state.get("current_follow_up_id")
        # But the turn *being recorded* (and evaluated - see the `evaluator.evaluate` call
        # below) is whichever was actually just answered: the root question on the first turn,
        # or the follow-up on a second one. Using the root's id/text unconditionally here would
        # make a follow-up's own answer show up in history under the original question's id and
        # text, as if the candidate had answered that instead.
        turn_question_id = follow_up_id or target["id"]
        turn_question_text = state.get("current_question_text") or target["target"]

        if answer is None or not answer.strip():
            # A blank answer has no evidence to evaluate - always worth one clarifying ask, but
            # still bounded by the same cap as any other follow-up: a candidate who submits
            # blank twice in a row must not be asked a third time indefinitely.
            at_cap = state["follow_up_count"] >= DEFAULT_MAX_FOLLOW_UPS
            history_entry = {
                "question_id": turn_question_id,
                "question": turn_question_text,
                "answer": answer or "",
                "evaluation": None,
                "root_question_id": target["id"],
            }
            if at_cap:
                return {
                    "evaluation": EvaluationDecision.ADVANCE.value,
                    "follow_up_question": None,
                    "history": state["history"] + [history_entry],
                    "assessed_target_ids": state["assessed_target_ids"] + [target["id"]],
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

        # Every other not-yet-assessed target, offered so the evaluator can report incidental
        # cross-target evidence (see `app.services.cross_target_evidence`) - e.g. the candidate
        # volunteers real Java experience while answering a Python question. Already-assessed
        # targets are excluded: they need no further evidence, and offering them back would
        # only invite a duplicate/pointless signal for something already resolved.
        other_targets = [
            (t["category"], t["target"])
            for t in state["coverage_targets"]
            if t["id"] != target["id"] and t["id"] not in state["assessed_target_ids"]
        ]
        # Latency instrumentation (adaptive-runtime review, item 6) - see `_make_select_target`
        # for the sibling measurements this composes with into one turn's total.
        evaluation_started_at = time.perf_counter()
        raw_result = await evaluator.evaluate(
            # The literal question text is whatever was actually asked for *this* turn - the
            # follow-up's own phrasing when this is a follow-up answer, not the root's runtime-
            # generated text. category/target/grounding stay root-derived: a follow-up doesn't
            # have its own category/target, it's still probing the same one.
            question_text=turn_question_text,
            category=target["category"],
            target=target["target"],
            grounding=target.get("grounding"),
            answer=answer,
            other_targets=other_targets,
        )
        logger.info(
            "interview_timing phase=answer_evaluation seconds=%.4f target=%s",
            time.perf_counter() - evaluation_started_at,
            target["id"],
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
                    "root_question_id": target["id"],
                }
            ],
        }
        if result.decision == EvaluationDecision.ADVANCE:
            # This target is done for the rest of the interview - a strong answer, an explicit
            # lack of experience, an inconclusive answer that used up its one follow-up, or
            # anything else the policy resolved to "move on" all mean the same thing here: the
            # target selector must not offer it again (see `select_target`/`select_next_target`
            # - "avoid unnecessary repeated probing" is enforced by this list, not by chance).
            update["assessed_target_ids"] = state["assessed_target_ids"] + [target["id"]]
        if result.decision == EvaluationDecision.FOLLOW_UP and result.follow_up_question:
            # Same reasoning as the blank-answer branch above: set it here, before the
            # `follow_up_question` node interrupts, not inside that node's own (never-reached
            # before resume) return value. When the graph instead forces an advance despite a
            # follow_up decision (the one-follow-up cap - see `resolve_follow_up_decision`),
            # `select_target` overwrites this with the next question's text before any
            # interrupt is hit, so setting it speculatively here is harmless in that case.
            update["current_question_text"] = result.follow_up_question

        # Cross-target evidence (see `app.services.cross_target_evidence`) is resolved
        # regardless of whether the *current* target itself just advanced or needs a
        # follow-up - a candidate volunteering evidence about a different target mid-answer is
        # independent of what happens to the target actually being asked about.
        if raw_result.cross_target_evidence:
            resolution_started_at = time.perf_counter()
            assessed_so_far = update.get("assessed_target_ids", state["assessed_target_ids"])
            resolution = resolve_cross_target_evidence(
                coverage_targets=state["coverage_targets"],
                current_target_id=target["id"],
                assessed_target_ids=assessed_so_far,
                cross_target_evidence=[
                    item.model_dump(mode="json") for item in raw_result.cross_target_evidence
                ],
                existing_hints=state.get("target_hints", {}),
            )
            logger.info(
                "interview_timing phase=cross_target_evidence seconds=%.4f "
                "newly_assessed=%d",
                time.perf_counter() - resolution_started_at,
                len(resolution.newly_assessed_ids),
            )
            if resolution.history_entries:
                update["history"] = update["history"] + resolution.history_entries
            if resolution.newly_assessed_ids:
                update["assessed_target_ids"] = assessed_so_far + resolution.newly_assessed_ids
            update["target_hints"] = resolution.updated_hints
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
    in `asked_question_ids` and `current_follow_up_id` exactly as a main question is recorded
    by `select_target` - so a follow-up is a first-class, auditable interview turn, not an
    untracked side effect. `evaluate_answer` uses `current_follow_up_id` (not the root target's
    id) as that turn's own `history[*].question_id`/`question` once it's answered.

    `current_question_id` itself deliberately stays as the parent target's id throughout (a
    follow-up is still "about" that same target, not a new one) - existing consumers (the
    candidate API's `current_question_id`, `_find_target` in this module, the report's
    per-question grouping via `root_question_id`) key off it and must keep working unchanged.
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
    """Route based on whether ``select_target`` actually found another target.

    Checking ``current_question_id is not None`` (rather than comparing counts) matters
    because ``select_target`` sets ``current_question_id`` the moment it *selects* a target,
    before it has been asked - comparing counts could treat the just-selected target as
    already-covered and skip straight to ``finish`` without ever asking it.
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


def build_interview_graph(
    evaluator: AnswerEvaluationService,
    question_service: QuestionGenerationService,
    policy: TargetSelectionPolicy = DEFAULT_POLICY,
) -> CompiledStateGraph:
    """Compile the interview graph with ``evaluator``/``question_service`` bound into it.

    Each call returns a fresh graph with its own :class:`InMemorySaver` checkpointer, so
    callers (see :func:`app.api.deps.get_interview_graph`) must build it once and reuse the
    same instance for the process lifetime - a new instance means a new, empty checkpoint
    store, and every existing ``thread_id`` would appear to have no state.
    """
    builder = StateGraph(InterviewGraphState)

    builder.add_node("select_target", _make_select_target(question_service, policy))
    builder.add_node("ask_question", ask_question)
    builder.add_node("evaluate_answer", _make_evaluate_answer(evaluator))
    builder.add_node("follow_up_question", follow_up_question)
    builder.add_node("finish", finish)

    builder.add_edge(START, "select_target")

    builder.add_conditional_edges(
        "select_target",
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
            "next_question": "select_target",
            "follow_up": "follow_up_question",
        },
    )

    builder.add_edge("follow_up_question", "evaluate_answer")

    builder.add_edge("finish", END)

    return builder.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    import asyncio

    from app.domain.interview_plan import (
        CoverageTarget,
        InterviewPlan,
        QuestionCategory,
        RequirementLevel,
    )
    from app.domain.interview_plan import EvidenceSource as _EvidenceSource
    from app.domain.occupation import OccupationMatch
    from app.llm.fake_client import FakeLLMClient

    async def _demo() -> None:
        graph = build_interview_graph(
            AnswerEvaluationService(llm=FakeLLMClient()),
            QuestionGenerationService(llm=FakeLLMClient()),
        )

        test_plan = InterviewPlan(
            job_id="job_123",
            role_title="Machine Learning Engineer",
            occupation_match=OccupationMatch(
                onet_soc_code="15-1252.00",
                title="Software Developers",
                score=1.0,
            ),
            coverage_targets=[
                CoverageTarget(
                    id="t1",
                    category=QuestionCategory.COMPETENCY,
                    target="Machine Learning",
                    requirement_level=RequirementLevel.REQUIRED,
                    source=_EvidenceSource.JOBSPEC,
                    priority=0,
                    grounding="JobSpec: Machine Learning",
                ),
                CoverageTarget(
                    id="t2",
                    category=QuestionCategory.TECHNOLOGY,
                    target="Machine Learning",
                    requirement_level=RequirementLevel.REQUIRED,
                    source=_EvidenceSource.ONET,
                    priority=0,
                    grounding="O*NET: Machine Learning",
                ),
                CoverageTarget(
                    id="t3",
                    category=QuestionCategory.TASK,
                    target="AI project development",
                    requirement_level=RequirementLevel.REQUIRED,
                    source=_EvidenceSource.ONET,
                    priority=0,
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
