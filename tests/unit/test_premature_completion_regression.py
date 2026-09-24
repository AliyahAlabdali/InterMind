"""End-to-end regression for the QA reproduction: one answer must not end the interview.

Job description: "AI Engineer with python, computer vision and NLP skills"
Coverage targets: Python, Computer Vision, Natural Language Processing (NLP) - all required.

Candidate answer:
    "I worked on a computer vision project using Python and PyTorch to train an object
     detection model."

The evaluator emitted ``explicit_lack`` for NLP with the note "No mention of experience with
Natural Language Processing" - an observation about the answer, dressed as a statement by the
candidate. ``explicit_lack`` was conclusive, so NLP was marked assessed without being asked,
all three required targets read as reached, and the interview ended after one answer with a
report claiming the candidate had denied NLP experience.

These tests drive the graph with a stub that emits that exact payload, so they prove the
runtime is safe *whatever* the evaluator returns - not merely that the schema and prompt now
discourage it.
"""

from __future__ import annotations

from langgraph.types import Command

from app.agents.interview_graph import build_graph_state, build_interview_graph
from app.domain.evaluation import (
    AnswerEvaluation,
    AnswerEvidenceType,
    CrossTargetEvidence,
    EvaluationDecision,
)
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
from app.services.answer_evaluation import AnswerEvaluationService
from app.services.question_generation import QuestionGenerationService
from app.services.report_scoring import (
    build_question_evaluations,
    build_unassessed_required_targets,
)

CV_ANSWER = (
    "I worked on a computer vision project using Python and PyTorch to train an object "
    "detection model."
)


def _target(id: str, name: str, priority: int) -> CoverageTarget:
    return CoverageTarget(
        id=id,
        category=QuestionCategory.TECHNOLOGY,
        target=name,
        requirement_level=RequirementLevel.REQUIRED,
        source=EvidenceSource.JOBSPEC,
        priority=priority,
        grounding="Job description requirement",
    )


def _plan() -> InterviewPlan:
    return InterviewPlan(
        job_id="job-ai",
        role_title="AI Engineer",
        occupation_match=OccupationMatch(
            onet_soc_code="15-1252.00", title="Software Developers", score=1.0
        ),
        coverage_targets=[
            _target("python", "Python", 0),
            _target("cv", "Computer Vision", 1),
            _target("nlp", "Natural Language Processing (NLP)", 2),
        ],
    )


class _QaReproductionClient:
    """Returns exactly what the real evaluator returned in the failing QA run.

    Python: demonstrated. Computer Vision: demonstrated cross-target (genuine - the answer
    describes it). NLP: ``explicit_lack`` cross-target, justified by the absence of any mention
    (the bug). Also generates questions, so one client can drive the whole graph.
    """

    def __init__(self) -> None:
        self.questions_asked: list[str] = []

    async def generate_structured(self, *, prompt, input_text, schema):
        if schema is GeneratedQuestionSet:
            category = target = None
            for line in input_text.splitlines():
                stripped = line.strip()
                for cat in ("COMPETENCY", "TECHNOLOGY", "TASK"):
                    if stripped.upper().startswith(f"{cat}:"):
                        category, target = cat.lower(), stripped.partition(":")[2].strip()
            self.questions_asked.append(target)
            return GeneratedQuestionSet(
                questions=[
                    GeneratedQuestion(
                        category=category, target=target, text=f"Tell me about {target}."
                    )
                ]
            )

        return AnswerEvaluation(
            score=0.7,
            evidence_type=AnswerEvidenceType.DEMONSTRATED,
            decision=EvaluationDecision.ADVANCE,
            follow_up_needed=False,
            follow_up_question=None,
            strengths=["Described a real computer vision project."],
            evidence=["train an object detection model"],
            cross_target_evidence=[
                CrossTargetEvidence(
                    target="Computer Vision",
                    evidence_type=AnswerEvidenceType.DEMONSTRATED,
                    note="I worked on a computer vision project using Python and PyTorch",
                ),
                CrossTargetEvidence(
                    target="Natural Language Processing (NLP)",
                    evidence_type=AnswerEvidenceType.EXPLICIT_LACK,
                    note="No mention of experience with Natural Language Processing.",
                ),
            ],
        )


async def _run_first_answer():
    client = _QaReproductionClient()
    graph = build_interview_graph(
        AnswerEvaluationService(llm=client), QuestionGenerationService(llm=client)
    )
    config = {"configurable": {"thread_id": "qa-premature"}}
    plan = _plan()

    await graph.ainvoke(build_graph_state(plan), config=config)
    state = await graph.ainvoke(Command(resume=CV_ANSWER), config=config)
    return plan, client, state


async def test_python_is_assessed_from_the_direct_answer():
    _, _, state = await _run_first_answer()
    assert "python" in state["assessed_target_ids"]


async def test_computer_vision_is_assessed_through_valid_cross_target_evidence():
    """The half of the payload that was always correct must keep working."""
    plan, _, state = await _run_first_answer()
    assert "cv" in state["assessed_target_ids"]

    cross = [t for t in state["history"] if t.get("assessment_method") == "cross_target"]
    assert [t["root_question_id"] for t in cross] == ["cv"]
    assert cross[0]["evaluation"]["evidence_type"] == "demonstrated"


async def test_nlp_is_not_assessed_from_an_answer_that_never_mentions_it():
    _, _, state = await _run_first_answer()
    assert "nlp" not in state["assessed_target_ids"]


async def test_no_lack_of_experience_claim_is_synthesized_for_nlp():
    _, _, state = await _run_first_answer()

    all_weaknesses = " ".join(
        weakness
        for turn in state["history"]
        for weakness in ((turn.get("evaluation") or {}).get("weaknesses") or [])
    )
    assert "do not have experience" not in all_weaknesses


async def test_the_interview_does_not_complete_after_one_answer():
    _, _, state = await _run_first_answer()
    assert state["status"] != "completed"


async def test_nlp_is_selected_as_the_next_target():
    """The whole point: the interview continues, and goes to the target it never covered."""
    _, client, state = await _run_first_answer()

    assert state["current_question_id"] == "nlp"
    assert client.questions_asked == ["Python", "Natural Language Processing (NLP)"]


async def test_nlp_remains_in_unassessed_required_targets():
    plan, _, state = await _run_first_answer()
    interview_state = InterviewState(
        job_id="job-ai",
        status=InterviewStatus.IN_PROGRESS,
        asked_question_ids=state["asked_question_ids"],
        history=state["history"],
    )

    evaluations = build_question_evaluations(plan, interview_state)
    unassessed = build_unassessed_required_targets(plan, evaluations)

    assert unassessed == ["Natural Language Processing (NLP)"]


# --- the previous target_id fix must remain intact --------------------------------------------


async def test_target_id_fix_still_holds_for_both_assessment_methods():
    """Assessed targets must not appear under "never reached", direct or cross-target, and the
    untouched one must."""
    plan, _, state = await _run_first_answer()
    interview_state = InterviewState(
        job_id="job-ai",
        status=InterviewStatus.IN_PROGRESS,
        asked_question_ids=state["asked_question_ids"],
        history=state["history"],
    )

    evaluations = build_question_evaluations(plan, interview_state)
    unassessed = set(build_unassessed_required_targets(plan, evaluations))
    by_target = {e.target: e for e in evaluations}

    assert by_target["Python"].target_id == "python"
    assert by_target["Python"].assessment_method == "direct"
    assert by_target["Computer Vision"].target_id == "cv"
    assert by_target["Computer Vision"].assessment_method == "cross_target"

    assert "Python" not in unassessed
    assert "Computer Vision" not in unassessed
    assert "Natural Language Processing (NLP)" in unassessed


# --- the schema contract that should stop this at the source ----------------------------------


def test_cross_target_schema_forbids_reporting_absence_as_evidence():
    """The contract fix. Field descriptions are serialised into the structured-output schema
    sent to OpenAI (see test_follow_up_routing_regression for the precedent), so this is where
    the evaluator is told that silence is not a finding. ``evidence_type`` previously carried no
    description at all - only the bare enum."""
    schema = AnswerEvaluation.model_json_schema()
    cross = schema["$defs"]["CrossTargetEvidence"]["properties"]

    evidence_type = cross["evidence_type"]
    description = " ".join(
        str(v) for v in (evidence_type.get("description"), evidence_type.get("title"))
    ).lower()
    assert "explicit_lack" in description
    assert "not mention" in description or "does not mention" in description

    note = cross["note"]["description"].lower()
    assert "candidate's own words" in note or "candidate" in note
