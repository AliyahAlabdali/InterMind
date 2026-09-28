"""End-to-end tests for the adaptive interview graph: target selection and question generation
happen at runtime, one target at a time, never by replaying a pre-generated question list.

Exercised directly through the compiled LangGraph (`build_interview_graph`/`build_graph_state`,
the same shape `app.services.interview_session.InterviewSessionService` drives) so internal
adaptive-loop state (`assessed_target_ids`, which target was actually selected) is directly
observable, not just its candidate-facing projection. Uses the real `FakeLLMClient` for answer
evaluation (so DEMONSTRATED/EXPLICIT_LACK/CLAIMED_UNVERIFIED classification is genuine, not
scripted) and a small spy client for question generation (so each call's requested target and
history context are directly observable).
"""

from __future__ import annotations

from langgraph.types import Command

from app.agents.interview_graph import build_graph_state, build_interview_graph
from app.domain.interview import InterviewState, InterviewStatus
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
from app.services.report_generation import ReportGenerationService
from app.services.report_narrative import ReportNarrativeService
from app.services.target_selection import TargetSelectionPolicy

DEMONSTRATED_ANSWER = (
    "I led a project where I diagnosed a race condition in a queue consumer, wrote a "
    "regression test to reproduce it, fixed the underlying lock ordering, and verified it "
    "in staging before shipping."
)
EXPLICIT_LACK_ANSWER = "I don't have experience with this."
CLAIMED_UNVERIFIED_ANSWER = "I don't remember the specifics, but I think I did something once."


class _SpyQuestionClient:
    """Records every question-generation call (requested target + full prompt input), then
    returns a deterministic, distinguishable question for it - so a test can tell exactly which
    target a given main question was generated for, and confirm it was generated *then*, not
    retrieved from anywhere static."""

    def __init__(self):
        self.calls: list[dict] = []

    async def generate_structured(self, *, prompt, input_text, schema):
        assert schema is GeneratedQuestionSet, f"unexpected schema requested: {schema}"
        category = target = None
        for line in input_text.splitlines():
            stripped = line.strip()
            for cat in ("COMPETENCY", "TECHNOLOGY", "TASK"):
                if stripped.upper().startswith(f"{cat}:"):
                    category, target = cat.lower(), stripped.partition(":")[2].strip()
        assert category is not None, f"no target line found in: {input_text!r}"
        self.calls.append({"input_text": input_text, "category": category, "target": target})
        return GeneratedQuestionSet(
            questions=[
                GeneratedQuestion(
                    category=category,
                    target=target,
                    text=f"[generated #{len(self.calls)}] Tell me about {target}.",
                )
            ]
        )


def _coverage_target(
    id: str,
    category: QuestionCategory,
    target: str,
    requirement_level: RequirementLevel,
    priority: int,
) -> CoverageTarget:
    return CoverageTarget(
        id=id,
        category=category,
        target=target,
        requirement_level=requirement_level,
        source=EvidenceSource.JOBSPEC,
        priority=priority,
        grounding="Job description requirement",
    )


def _make_plan(coverage_targets: list[CoverageTarget], job_id: str = "job-1") -> InterviewPlan:
    return InterviewPlan(
        job_id=job_id,
        role_title="Software Developer",
        occupation_match=OccupationMatch(
            onet_soc_code="15-1252.00", title="Software Developers", score=1.0
        ),
        coverage_targets=coverage_targets,
    )


def _mixed_plan(scrambled: bool = False) -> InterviewPlan:
    """One required competency, one required + one preferred technology, one required task -
    enough categories/requirement-tiers to exercise the full selection policy."""
    communication = _coverage_target(
        "communication", QuestionCategory.COMPETENCY, "Communication", RequirementLevel.REQUIRED, 0
    )
    python = _coverage_target(
        "python", QuestionCategory.TECHNOLOGY, "Python", RequirementLevel.REQUIRED, 0
    )
    excel = _coverage_target(
        "excel", QuestionCategory.TECHNOLOGY, "Excel", RequirementLevel.PREFERRED, 1000
    )
    ship_features = _coverage_target(
        "ship_features",
        QuestionCategory.TASK,
        "Ship backend features.",
        RequirementLevel.REQUIRED,
        0,
    )
    targets = (
        [excel, ship_features, python, communication]
        if scrambled
        else [communication, python, excel, ship_features]
    )
    return _make_plan(targets)


def _graph(spy: _SpyQuestionClient, policy: TargetSelectionPolicy | None = None):
    kwargs = {} if policy is None else {"policy": policy}
    return build_interview_graph(
        AnswerEvaluationService(llm=FakeLLMClient()),
        QuestionGenerationService(llm=spy),
        **kwargs,
    )


def _config(thread_id: str = "t1") -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _python_java_plan(job_id: str = "job-cross-target") -> InterviewPlan:
    """Two required technology targets - enough to exercise cross-target evidence discovered
    while answering the first (Python) about the second (Java), see the Copilot review this
    fixes: `app.services.cross_target_evidence`."""
    python = _coverage_target(
        "python", QuestionCategory.TECHNOLOGY, "Python", RequirementLevel.REQUIRED, 0
    )
    java = _coverage_target(
        "java", QuestionCategory.TECHNOLOGY, "Java", RequirementLevel.REQUIRED, 1
    )
    return _make_plan([python, java], job_id=job_id)


# --- 1: the first question is generated from the selected initial target -------------------


async def test_first_question_is_generated_from_the_selected_initial_target():
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    result = await graph.ainvoke(build_graph_state(_mixed_plan()), config=_config())

    assert len(spy.calls) == 1
    # Communication is the only competency (category order: competency first) - the highest-
    # priority target, selected dynamically, not read off any fixed index.
    assert spy.calls[0]["target"] == "Communication"
    assert result["current_question_id"] == "communication"
    assert result["current_question_text"] == "[generated #1] Tell me about Communication."
    # No history yet - the very first question has nothing to draw on.
    assert "INTERVIEW_HISTORY:" not in spy.calls[0]["input_text"]


# --- 2: the system evaluates the answer before selecting the next main target --------------


async def test_answer_is_evaluated_before_a_new_target_is_selected():
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    config = _config()
    await graph.ainvoke(build_graph_state(_mixed_plan()), config=config)

    result = await graph.ainvoke(Command(resume=DEMONSTRATED_ANSWER), config=config)

    # The strong answer was scored (recorded in history with a real evaluation) *before* moving
    # on - the next target is only selected once that evaluation resolved to "advance".
    assert result["history"][0]["evaluation"]["decision"] == "advance"
    assert result["history"][0]["evaluation"]["score"] >= 0.8
    assert result["assessed_target_ids"] == ["communication"]
    assert len(spy.calls) == 2  # a second, freshly generated question followed


# --- 3: a strong answer marks the target sufficiently assessed and moves on ----------------


async def test_a_strong_answer_marks_the_target_assessed_and_moves_to_a_new_one():
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    config = _config()
    await graph.ainvoke(build_graph_state(_mixed_plan()), config=config)

    result = await graph.ainvoke(Command(resume=DEMONSTRATED_ANSWER), config=config)

    assert "communication" in result["assessed_target_ids"]
    assert result["current_question_id"] != "communication"
    assert spy.calls[1]["target"] != "Communication"


# --- 4: an explicit lack of experience does not cause unnecessary repeated probing ---------


async def test_explicit_lack_of_experience_advances_without_a_follow_up():
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    config = _config()
    await graph.ainvoke(build_graph_state(_mixed_plan()), config=config)

    result = await graph.ainvoke(Command(resume=EXPLICIT_LACK_ANSWER), config=config)

    # Advanced immediately - no follow-up interrupt was raised for this target.
    assert result["assessed_target_ids"] == ["communication"]
    assert len(result["history"]) == 1
    assert result["history"][0]["evaluation"]["decision"] == "advance"
    assert result["history"][0]["evaluation"]["evidence_type"] == "explicit_lack"
    # Moved straight on to a new target - never asked again about Communication.
    assert result["current_question_id"] != "communication"
    assert len(spy.calls) == 2


# --- 5: an ambiguous/claimed-unverified answer can trigger a targeted follow-up ------------


async def test_claimed_unverified_answer_triggers_a_follow_up_on_the_same_target():
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    config = _config()
    await graph.ainvoke(build_graph_state(_mixed_plan()), config=config)

    result = await graph.ainvoke(Command(resume=CLAIMED_UNVERIFIED_ANSWER), config=config)

    assert result["evaluation"] == "follow_up"
    assert result["assessed_target_ids"] == []  # not resolved yet - still in progress
    assert result["current_question_id"] == "communication"  # still the same root target
    # A follow-up never calls the question generator again - it's the evaluator's own
    # answer-grounded follow-up question, not a newly generated main question.
    assert len(spy.calls) == 1


# --- 6: follow-ups remain attached to the correct root target ------------------------------


async def test_follow_up_turn_is_attached_to_the_correct_root_target():
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    config = _config()
    await graph.ainvoke(build_graph_state(_mixed_plan()), config=config)
    await graph.ainvoke(Command(resume=CLAIMED_UNVERIFIED_ANSWER), config=config)

    result = await graph.ainvoke(Command(resume=DEMONSTRATED_ANSWER), config=config)

    assert len(result["history"]) == 2
    original_turn, follow_up_turn = result["history"]
    assert original_turn["root_question_id"] == "communication"
    assert follow_up_turn["root_question_id"] == "communication"
    assert follow_up_turn["question_id"] != "communication"  # the follow-up's own distinct id
    # The follow-up resolved the target - now it's assessed and the interview moved on.
    assert result["assessed_target_ids"] == ["communication"]
    assert result["current_question_id"] != "communication"


# --- 7/9: the next main question is generated dynamically, never a replay of plan order -----


async def test_next_question_is_generated_dynamically_not_replayed_from_the_plan_list():
    """Test 9 (regression suite): the coverage_targets list is given in a scrambled order
    (technology/task before competency) - if the graph were "just replaying" that list order,
    the first question would be about Excel or the task. It must still be Communication
    (correct category-then-priority order), proving selection is recomputed, not indexed."""
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    config = _config()

    first = await graph.ainvoke(build_graph_state(_mixed_plan(scrambled=True)), config=config)
    assert first["current_question_id"] == "communication"

    second = await graph.ainvoke(Command(resume=DEMONSTRATED_ANSWER), config=config)
    # Test 7: a brand-new question, generated for the newly selected target (Python - required,
    # sorts before the preferred Excel within the technology category).
    assert second["current_question_id"] == "python"
    assert spy.calls[1]["target"] == "Python"
    assert second["current_question_text"] == "[generated #2] Tell me about Python."


# --- 8: the next main question receives relevant interview history -------------------------


async def test_next_main_question_generation_receives_prior_history():
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    config = _config()
    await graph.ainvoke(build_graph_state(_mixed_plan()), config=config)

    await graph.ainvoke(Command(resume=DEMONSTRATED_ANSWER), config=config)

    assert len(spy.calls) == 2
    second_call_input = spy.calls[1]["input_text"]
    assert "INTERVIEW_HISTORY:" in second_call_input
    assert "PREVIOUS_Q: [generated #1] Tell me about Communication." in second_call_input
    assert f"PREVIOUS_A: {DEMONSTRATED_ANSWER}" in second_call_input


# --- 10: already-assessed targets are not selected again unless clarification is required --


async def test_an_assessed_target_is_never_selected_again():
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    config = _config()
    await graph.ainvoke(build_graph_state(_mixed_plan()), config=config)
    await graph.ainvoke(Command(resume=DEMONSTRATED_ANSWER), config=config)  # Communication done
    result = await graph.ainvoke(Command(resume=DEMONSTRATED_ANSWER), config=config)  # Python done

    assert set(result["assessed_target_ids"]) == {"communication", "python"}
    targets_asked_about = [call["target"] for call in spy.calls]
    assert targets_asked_about.count("Communication") == 1
    assert targets_asked_about.count("Python") == 1


# --- 11: required targets are prioritized correctly -----------------------------------------


async def test_required_targets_are_asked_about_before_preferred_ones():
    spy = _SpyQuestionClient()
    # A technology budget of 1 means only one technology target can ever be asked about - this
    # isolates the required-vs-preferred ordering question from category ordering (under the
    # default, larger budget, Excel would still eventually be reached; here it must not be,
    # because Python (required) always wins the single available slot).
    policy = TargetSelectionPolicy(competency_budget=1, technology_budget=1, task_budget=1)
    graph = _graph(spy, policy=policy)
    config = _config()
    await graph.ainvoke(build_graph_state(_mixed_plan()), config=config)
    await graph.ainvoke(Command(resume=DEMONSTRATED_ANSWER), config=config)  # -> Python
    await graph.ainvoke(Command(resume=DEMONSTRATED_ANSWER), config=config)  # -> task

    targets_in_order = [call["target"] for call in spy.calls]
    assert targets_in_order[0] == "Communication"
    assert targets_in_order[1] == "Python"  # required technology before preferred Excel
    assert "Excel" not in targets_in_order  # never reached - the one technology slot went to Python


# --- 12: the interview finishes once required coverage is satisfied ------------------------


async def test_interview_finishes_once_required_coverage_is_satisfied():
    spy = _SpyQuestionClient()
    # Budgets sized exactly to the plan's required targets (1 competency, 1 technology, 1
    # task) - the preferred "Excel" technology never fits, and the interview still finishes
    # cleanly rather than hanging or erroring.
    policy = TargetSelectionPolicy(competency_budget=1, technology_budget=1, task_budget=1)
    graph = _graph(spy, policy=policy)
    config = _config()

    await graph.ainvoke(build_graph_state(_mixed_plan()), config=config)
    await graph.ainvoke(Command(resume=DEMONSTRATED_ANSWER), config=config)
    await graph.ainvoke(Command(resume=DEMONSTRATED_ANSWER), config=config)
    finished = await graph.ainvoke(Command(resume=DEMONSTRATED_ANSWER), config=config)

    assert finished["status"] == "completed"
    assert finished["current_question_id"] is None
    assert set(finished["assessed_target_ids"]) == {"communication", "python", "ship_features"}
    assert "Excel" not in [call["target"] for call in spy.calls]


async def test_interview_length_is_an_outcome_not_a_fixed_count():
    """The same coverage pool, under two different (still deterministic) policies, produces two
    different numbers of main questions - the count is genuinely computed from the interview's
    progress and the policy, never a hardcoded plan length."""
    small_policy = TargetSelectionPolicy(competency_budget=1, technology_budget=1, task_budget=1)
    large_policy = TargetSelectionPolicy(competency_budget=1, technology_budget=2, task_budget=1)

    small_spy, large_spy = _SpyQuestionClient(), _SpyQuestionClient()
    small_graph = _graph(small_spy, policy=small_policy)
    large_graph = _graph(large_spy, policy=large_policy)

    for graph in (small_graph, large_graph):
        config = _config()
        state = await graph.ainvoke(build_graph_state(_mixed_plan()), config=config)
        while state["status"] != "completed":
            state = await graph.ainvoke(Command(resume=DEMONSTRATED_ANSWER), config=config)

    assert len(small_spy.calls) == 3  # competency + required technology + task
    assert len(large_spy.calls) == 4  # ...plus the preferred technology, now within budget


# --- Copilot review, MUST FIX 1: cross-target evidence -------------------------------------
#
# A candidate answering a question about one target sometimes volunteers real evidence about a
# *different* target - e.g. answering a Python question but also mentioning extensive Java
# experience. Without this, that evidence was simply lost. See
# app.services.cross_target_evidence for the deterministic, LLM-free resolution this exercises
# end-to-end here (the LLM-facing classification itself is covered directly in
# tests/unit/test_answer_grounding.py).

STRONG_JAVA_MENTION_ANSWER = (
    "I built a Python microservice using FastAPI, wrote extensive integration tests, and "
    "deployed it to production. I also have extensive Java experience, having built and "
    "maintained several production services with it."
)
CASUAL_JAVA_MENTION_ANSWER = (
    "I built a Python microservice using FastAPI, wrote extensive integration tests, and "
    "deployed it to production. I've also used Java a little bit."
)


async def test_1_evidence_for_one_target_can_affect_a_different_target():
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    config = _config()
    await graph.ainvoke(build_graph_state(_python_java_plan()), config=config)

    result = await graph.ainvoke(Command(resume=STRONG_JAVA_MENTION_ANSWER), config=config)

    java_turn = next(t for t in result["history"] if t["root_question_id"] == "java")
    assert java_turn["answer"]  # a real, non-empty signal was recorded for Java
    assert java_turn["question_id"] == "java"


async def test_2_strong_incidental_evidence_marks_the_other_target_sufficiently_assessed():
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    config = _config()
    await graph.ainvoke(build_graph_state(_python_java_plan()), config=config)

    result = await graph.ainvoke(Command(resume=STRONG_JAVA_MENTION_ANSWER), config=config)

    assert "python" in result["assessed_target_ids"]
    assert "java" in result["assessed_target_ids"]
    assert result["status"] == "completed"  # nothing left - both targets resolved
    # Java's own question text was never generated at all - it was never asked directly.
    assert len(spy.calls) == 1
    assert all(call["target"] != "Java" for call in spy.calls)

    java_turn = next(t for t in result["history"] if t["root_question_id"] == "java")
    assert java_turn["evaluation"]["decision"] == "advance"
    assert java_turn["evaluation"]["evidence_type"] == "demonstrated"


async def test_3_a_casual_mention_does_not_incorrectly_mark_the_target_assessed():
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    config = _config()
    await graph.ainvoke(build_graph_state(_python_java_plan()), config=config)

    result = await graph.ainvoke(Command(resume=CASUAL_JAVA_MENTION_ANSWER), config=config)

    assert "python" in result["assessed_target_ids"]
    assert "java" not in result["assessed_target_ids"]
    # The selector picked Java up normally afterward - a real question was generated for it.
    assert result["current_question_id"] == "java"
    assert len(spy.calls) == 2
    assert spy.calls[1]["target"] == "Java"
    assert result["target_hints"]["java"]["evidence_type"] == "claimed_unverified"


async def test_4_explicit_lack_of_the_current_target_does_not_invent_cross_target_evidence():
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    config = _config()
    await graph.ainvoke(build_graph_state(_python_java_plan()), config=config)

    result = await graph.ainvoke(Command(resume=EXPLICIT_LACK_ANSWER), config=config)

    assert result["assessed_target_ids"] == ["python"]
    assert "java" not in result["assessed_target_ids"]
    assert result["target_hints"] == {}  # no spurious hint invented for Java either
    assert result["current_question_id"] == "java"  # asked about normally, from scratch


async def test_5_cross_target_resolution_is_deterministic():
    async def _run() -> tuple[list[str], str | None]:
        spy = _SpyQuestionClient()
        graph = _graph(spy)
        config = _config()
        await graph.ainvoke(build_graph_state(_python_java_plan()), config=config)
        result = await graph.ainvoke(Command(resume=STRONG_JAVA_MENTION_ANSWER), config=config)
        return sorted(result["assessed_target_ids"]), result["current_question_id"]

    first = await _run()
    second = await _run()
    assert first == second


async def test_6_cross_target_resolution_flows_into_the_final_report():
    """Item 8 (report coverage)/item 9K (report generation stays compatible with adaptive
    history): a target resolved purely via cross-target evidence, never asked directly, must
    still appear in the generated report - see the app.services.report_scoring fix this pins
    down at the full graph -> report pipeline level, not just the pure-function level."""
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    config = _config()
    plan = _python_java_plan()
    await graph.ainvoke(build_graph_state(plan), config=config)
    raw_state = await graph.ainvoke(Command(resume=STRONG_JAVA_MENTION_ANSWER), config=config)

    interview_state = InterviewState(
        job_id=raw_state["job_id"],
        status=InterviewStatus(raw_state["status"]),
        turn_index=len(raw_state["asked_question_ids"]),
        history=raw_state["history"],
        current_question_id=raw_state["current_question_id"],
        current_question_text=raw_state["current_question_text"],
        asked_question_ids=raw_state["asked_question_ids"],
    )
    report_service = ReportGenerationService(narrative=ReportNarrativeService(llm=FakeLLMClient()))
    report = await report_service.generate(interview_id="i1", plan=plan, state=interview_state)

    targets = {qe.target for qe in report.question_evaluations}
    assert targets == {"Python", "Java"}
    java_eval = next(qe for qe in report.question_evaluations if qe.target == "Java")
    assert java_eval.evidence_type.value == "demonstrated"
    assert {c.name for c in report.competencies} == {"Python", "Java"}


# --- Copilot review, MUST FIX 2: runtime question generation is grounded in the JD ----------


async def test_runtime_question_generation_receives_jd_context():
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    config = _config()

    plan = _mixed_plan()
    await graph.ainvoke(build_graph_state(plan), config=config)

    assert len(spy.calls) == 1
    sent = spy.calls[0]["input_text"]
    assert "JD_CONTEXT:" in sent
    # Role/seniority (plan.role_title/seniority default to "Software Developer"/unknown here,
    # so seniority is correctly omitted - see the next test for a seniority-bearing plan).
    assert "ROLE_TITLE: Software Developer" in sent
    # The other coverage targets - required/preferred technologies, competencies,
    # responsibilities - all reach the prompt, not just the bare selected target/role.
    assert "REQUIRED_TECHNOLOGIES: Python" in sent
    assert "PREFERRED_TECHNOLOGIES: Excel" in sent
    assert "COMPETENCIES: Communication" in sent
    assert "RESPONSIBILITIES:" in sent
    assert "Ship backend features." in sent
    # The current target's own requirement level/grounding is included too.
    assert "CURRENT_TARGET_REQUIREMENT_LEVEL: required" in sent
    assert "CURRENT_TARGET_GROUNDING:" in sent
    # JD context is never itself a target - only Communication (the actual selected target)
    # was requested; Python/Excel/the task appear only inside JD_CONTEXT above, never as a
    # separate requested-target line of their own.
    assert "COMPETENCY: Communication" in sent
    assert "TECHNOLOGY: Python" not in sent
    assert "TASK: Ship backend features." not in sent


async def test_runtime_question_generation_includes_seniority_when_known():
    from app.domain.job import Seniority

    plan = InterviewPlan(
        job_id="job-seniority",
        role_title="Senior Backend Engineer",
        seniority=Seniority.SENIOR,
        occupation_match=OccupationMatch(
            onet_soc_code="15-1252.00", title="Software Developers", score=1.0
        ),
        coverage_targets=[
            _coverage_target(
                "python", QuestionCategory.TECHNOLOGY, "Python", RequirementLevel.REQUIRED, 0
            )
        ],
    )
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    await graph.ainvoke(build_graph_state(plan), config=_config())

    sent = spy.calls[0]["input_text"]
    assert "SENIORITY: senior" in sent


async def test_jd_context_never_becomes_a_new_target():
    """O*NET context already has this guarantee (see test_question_generation.py) - JD context
    must have the same one: it's background for phrasing, never itself something a question
    must be generated for."""
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    await graph.ainvoke(build_graph_state(_mixed_plan()), config=_config())

    assert len(spy.calls) == 1  # exactly one question generated, for the one selected target
    assert spy.calls[0]["target"] == "Communication"


async def test_a_prior_non_conclusive_cross_target_hint_reaches_that_targets_own_question():
    """A casual mention recorded as a hint (see the cross-target tests above) is not wasted
    once that target is later actually asked about - the generator sees it as context."""
    spy = _SpyQuestionClient()
    graph = _graph(spy)
    config = _config()
    await graph.ainvoke(build_graph_state(_python_java_plan()), config=config)
    await graph.ainvoke(Command(resume=CASUAL_JAVA_MENTION_ANSWER), config=config)

    assert spy.calls[1]["target"] == "Java"
    assert "PRIOR_MENTION" in spy.calls[1]["input_text"]
    assert "claimed_unverified" in spy.calls[1]["input_text"]
