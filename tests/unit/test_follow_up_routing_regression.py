"""Regression tests for the adaptive follow-up routing bug found in end-to-end QA.

The symptom: during real interviews, short/insufficient answers were evaluated as
``decision=follow_up`` and ``resolve_follow_up_decision`` agreed, yet the graph went straight
from ``phase=answer_evaluation`` to ``phase=target_selection`` - the follow-up node was never
entered. The graph wiring and the resolver were both correct; the defect was upstream, in the
contract sent to the model (see ``test_schema_never_gates_follow_up_question_on_the_decision``,
which is the test that actually catches it).

Every other test here pins the routing behaviour itself, so a future change to the graph, the
resolver or the follow-up identity scheme cannot silently reintroduce the symptom.
"""

from __future__ import annotations

from langgraph.types import Command

from app.agents.interview_graph import build_graph_state, build_interview_graph
from app.domain.evaluation import (
    AnswerEvaluation,
    AnswerEvidenceType,
    EvaluationDecision,
    resolve_follow_up_decision,
)
from app.domain.interview_plan import (
    CoverageTarget,
    EvidenceSource,
    GeneratedQuestion,
    GeneratedQuestionSet,
    InterviewPlan,
    QuestionCategory,
    RequirementLevel,
)
from app.domain.occupation import OccupationMatch
from app.llm.fake_client import FakeLLMClient
from app.services.answer_evaluation import AnswerEvaluationService
from app.services.question_generation import QuestionGenerationService

# Substantive but incomplete: leaves a concrete, specific detail unexplored, which is exactly
# the shape that must earn a follow-up.
PARTIAL_ANSWER = (
    "We had a slow endpoint because of an inefficient database query. I added an index and "
    "reduced response time from several seconds to under one second."
)
EXPLICIT_LACK_ANSWER = "I don't have experience with this."


class _QuestionClient:
    """Deterministic question generator that records how many main questions were produced."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate_structured(self, *, prompt, input_text, schema):
        category = target = None
        for line in input_text.splitlines():
            stripped = line.strip()
            for cat in ("COMPETENCY", "TECHNOLOGY", "TASK"):
                if stripped.upper().startswith(f"{cat}:"):
                    category, target = cat.lower(), stripped.partition(":")[2].strip()
        self.calls.append(target)
        return GeneratedQuestionSet(
            questions=[
                GeneratedQuestion(
                    category=category,
                    target=target,
                    text=f"[main #{len(self.calls)}] Tell me about {target}.",
                )
            ]
        )


def _target(id: str, category: QuestionCategory, name: str, priority: int) -> CoverageTarget:
    return CoverageTarget(
        id=id,
        category=category,
        target=name,
        requirement_level=RequirementLevel.REQUIRED,
        source=EvidenceSource.JOBSPEC,
        priority=priority,
        grounding="Job description requirement",
    )


def _plan(job_id: str = "job-followup") -> InterviewPlan:
    return InterviewPlan(
        job_id=job_id,
        role_title="Software Developer",
        occupation_match=OccupationMatch(
            onet_soc_code="15-1252.00", title="Software Developers", score=1.0
        ),
        coverage_targets=[
            _target("sql", QuestionCategory.TECHNOLOGY, "SQL", 0),
            _target("python", QuestionCategory.TECHNOLOGY, "Python", 1),
        ],
    )


def _graph(question_client: _QuestionClient):
    return build_interview_graph(
        AnswerEvaluationService(llm=FakeLLMClient()),
        QuestionGenerationService(llm=question_client),
    )


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


# --- the contract that actually broke -------------------------------------------------------


def test_schema_never_gates_follow_up_question_on_the_decision():
    """The root cause, pinned.

    ``AnswerEvaluation`` is handed to OpenAI as ``response_format``, so every field
    ``description`` is serialised into the structured-output contract the model must satisfy -
    alongside, and competing with, the prompt. ``follow_up_question``'s description used to read
    "Set only when follow_up_needed is true."

    That is a circular dependency with the system's own policy: ``resolve_follow_up_decision``
    exists precisely because the model's one-shot ``decision`` under-calls follow-ups, and it
    re-derives the call from ``follow_up_question``. Gating that field on ``follow_up_needed``
    (which is just ``decision`` restated) meant the evidence the override needs was withheld in
    exactly the turns the override exists for - so the override could never fire, and the graph
    always advanced.

    Nothing in the unit suite caught it because ``FakeLLMClient`` constructs
    ``AnswerEvaluation`` in Python and never reads a field description.
    """
    schema = AnswerEvaluation.model_json_schema()
    description = schema["properties"]["follow_up_question"]["description"].lower()

    assert "regardless" in description, (
        "follow_up_question's description must tell the model to populate it independently of "
        "`decision`/`follow_up_needed` - the system's follow-up policy reads this field to "
        "override `decision`, so gating it on `decision` makes the override unreachable."
    )
    # The specific wording that caused the bug, and any restatement of it.
    assert "only when follow_up_needed is true" not in description
    assert "set only when" not in description

    # Removing the contradiction was necessary but not sufficient: measured against the real
    # model, a thin answer still only carried a follow-up question about 2 times in 5, because
    # nothing told it that a `claimed_unverified`/`partial` answer always leaves something to
    # ask. Tying the field to the classification the model already gets right took that to
    # roughly 4 in 5. Keep both clauses.
    assert "claimed_unverified" in description
    assert "explicit_lack" in description


def test_resolver_can_still_follow_up_when_the_model_itself_said_advance():
    """The override the schema fix restores: a model turn that leans ``advance`` but supplies a
    concrete follow-up question must still be resolved to ``follow_up``."""
    evaluation = AnswerEvaluation(
        score=0.45,
        evidence_type=AnswerEvidenceType.PARTIAL,
        decision=EvaluationDecision.ADVANCE,
        follow_up_needed=False,
        follow_up_question="Which index did you add, and how did you measure the improvement?",
        weaknesses=["No numbers given for the improvement."],
    )

    resolved = resolve_follow_up_decision(evaluation, follow_ups_used=0)

    assert resolved.decision == EvaluationDecision.FOLLOW_UP
    assert resolved.follow_up_question


# --- routing through the real compiled graph ------------------------------------------------


async def test_answer_needing_a_follow_up_routes_to_the_follow_up_node():
    """(1) A follow-up decision must actually reach ``follow_up_question`` - not
    ``select_target``."""
    questions = _QuestionClient()
    graph = _graph(questions)
    config = _config("routing-1")

    await graph.ainvoke(build_graph_state(_plan()), config=config)
    state = await graph.ainvoke(Command(resume=PARTIAL_ANSWER), config=config)

    assert state["evaluation"] == EvaluationDecision.FOLLOW_UP.value
    snapshot = await graph.aget_state(config)
    assert snapshot.next == ("follow_up_question",)
    # The decisive assertion: no second main question was generated, so target selection did
    # not run. This is the exact symptom QA reported.
    assert len(questions.calls) == 1

    interrupt = state["__interrupt__"][0].value
    assert interrupt["type"] == "follow_up"


async def test_follow_up_carries_the_root_question_context():
    """(2) The follow-up is about the same target, and says so."""
    graph = _graph(_QuestionClient())
    config = _config("routing-2")

    await graph.ainvoke(build_graph_state(_plan()), config=config)
    state = await graph.ainvoke(Command(resume=PARTIAL_ANSWER), config=config)

    interrupt = state["__interrupt__"][0].value
    assert interrupt["question_id"] == "sql"
    # `current_question_id` stays pinned to the target, never repointed at the follow-up.
    assert state["current_question_id"] == "sql"
    # The candidate is shown the follow-up's own wording, not the original question again.
    assert state["current_question_text"] == interrupt["question"]
    assert state["current_question_text"] != "[main #1] Tell me about SQL."


async def test_follow_up_has_its_own_distinct_question_id():
    """(3) A follow-up is a first-class, separately identifiable turn."""
    graph = _graph(_QuestionClient())
    config = _config("routing-3")

    await graph.ainvoke(build_graph_state(_plan()), config=config)
    state = await graph.ainvoke(Command(resume=PARTIAL_ANSWER), config=config)

    interrupt = state["__interrupt__"][0].value
    assert interrupt["follow_up_id"] != interrupt["question_id"]
    assert interrupt["follow_up_id"] not in {"sql", "python"}


async def test_follow_up_turn_records_the_correct_root_question_id():
    """(4) History must attribute the follow-up's answer to the follow-up, while still
    grouping it under the target it belongs to."""
    graph = _graph(_QuestionClient())
    config = _config("routing-4")

    await graph.ainvoke(build_graph_state(_plan()), config=config)
    state = await graph.ainvoke(Command(resume=PARTIAL_ANSWER), config=config)
    follow_up_id = state["__interrupt__"][0].value["follow_up_id"]
    state = await graph.ainvoke(
        Command(resume="I used EXPLAIN and compared p95 latency."), config=config
    )

    sql_turns = [t for t in state["history"] if t["root_question_id"] == "sql"]
    assert len(sql_turns) == 2, "the original answer and the follow-up answer are both turns"
    assert sql_turns[0]["question_id"] == "sql"
    assert sql_turns[1]["question_id"] == follow_up_id
    assert all(t["root_question_id"] == "sql" for t in sql_turns)


async def test_graph_returns_to_target_selection_after_the_allowed_follow_up():
    """(5) The follow-up is bounded: after one, the interview moves on to the next target."""
    questions = _QuestionClient()
    graph = _graph(questions)
    config = _config("routing-5")

    await graph.ainvoke(build_graph_state(_plan()), config=config)
    await graph.ainvoke(Command(resume=PARTIAL_ANSWER), config=config)
    state = await graph.ainvoke(Command(resume=PARTIAL_ANSWER), config=config)

    # Second main question generated => target selection ran.
    assert len(questions.calls) == 2
    assert questions.calls[1] == "Python"
    assert state["current_question_id"] == "python"
    assert "sql" in state["assessed_target_ids"]
    assert state["follow_up_count"] == 0, "the counter resets for the newly selected target"


async def test_answer_with_nothing_to_probe_still_advances_without_a_follow_up():
    """(6a) The anti-gaming path is untouched: an explicit lack of experience has nothing
    concrete to ask, so it must not produce a follow-up."""
    questions = _QuestionClient()
    graph = _graph(questions)
    config = _config("routing-6a")

    await graph.ainvoke(build_graph_state(_plan()), config=config)
    state = await graph.ainvoke(Command(resume=EXPLICIT_LACK_ANSWER), config=config)

    assert state["evaluation"] == EvaluationDecision.ADVANCE.value
    assert len(questions.calls) == 2, "advanced straight to the next target"
    assert "sql" in state["assessed_target_ids"]


async def test_interview_still_finishes_when_every_target_is_assessed():
    """(6b) The finish path still works."""
    graph = _graph(_QuestionClient())
    config = _config("routing-6b")

    await graph.ainvoke(build_graph_state(_plan()), config=config)
    state = await graph.ainvoke(Command(resume=EXPLICIT_LACK_ANSWER), config=config)
    state = await graph.ainvoke(Command(resume=EXPLICIT_LACK_ANSWER), config=config)

    assert state["status"] == "completed"
    assert state["current_question_id"] is None
    assert set(state["assessed_target_ids"]) == {"sql", "python"}
