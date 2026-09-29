"""A follow-up is evaluated as a continuation of its own exchange, not as a fresh answer.

From a real interview: the main answer named the evaluation metrics used, the follow-up went on
to describe the implementation, and the follow-up's evaluation - which saw only its own turn -
recorded "the answer lacked specific details about the performance evaluation metrics used".
The report then repeated that, contradicting evidence the same exchange had already produced.

These pin the plumbing that fixes it: the earlier same-root turns reach the evaluator, nothing
else does, and a main question's input is untouched. What the model then *writes* with that
context is the model's own behaviour and is asserted here only where a deterministic client can
honestly stand in for it (see `test_the_prompt_forbids_calling_established_facts_missing`).
"""

from __future__ import annotations

import pytest
from langgraph.types import Command
from pydantic import BaseModel

from app.agents.interview_graph import build_graph_state, build_interview_graph
from app.domain.evaluation import AnswerEvaluation, AnswerEvidenceType, EvaluationDecision
from app.domain.interview_plan import (
    CoverageTarget,
    EvidenceSource,
    InterviewPlan,
    QuestionCategory,
    RequirementLevel,
)
from app.domain.occupation import OccupationMatch
from app.llm.fake_client import FakeLLMClient
from app.llm.prompts import load_prompt
from app.services.answer_evaluation import AnswerEvaluationService
from app.services.question_generation import QuestionGenerationService

MAIN_ANSWER = (
    "My graduation project used a computer vision model, YOLO, and we evaluated it with mean "
    "average precision, mAP@50 and mAP@95."
)
FOLLOW_UP_ANSWER = (
    "I trained it with transfer learning, adapted a pretrained model, and evaluated it on "
    "unseen test sets. The performance was roughly two to three times the baseline."
)


class RecordingLLMClient:
    """Records every evaluation input, and answers with a fixed, valid evaluation."""

    def __init__(self, evaluation: AnswerEvaluation | None = None) -> None:
        self.inputs: list[str] = []
        self._evaluation = evaluation or AnswerEvaluation(
            score=0.45,
            evidence_type=AnswerEvidenceType.PARTIAL,
            decision=EvaluationDecision.ADVANCE,
            strengths=["Described the approach."],
            weaknesses=["The measured values were never given."],
            evidence=["trained it with transfer learning"],
            follow_up_needed=False,
            follow_up_question=None,
        )

    async def generate_structured(self, *, prompt, input_text, schema: type[BaseModel]):
        self.inputs.append(input_text)
        return self._evaluation


# --- the evaluator's own input ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_prior_same_root_turns_reach_the_evaluator():
    llm = RecordingLLMClient()

    await AnswerEvaluationService(llm=llm).evaluate(
        question_text="Can you explain how you implemented it and share some results?",
        category="technology",
        target="Computer Vision",
        answer=FOLLOW_UP_ANSWER,
        prior_exchange=[("Walk me through a recent computer vision project.", MAIN_ANSWER)],
    )

    sent = llm.inputs[0]
    assert "EARLIER_IN_THIS_EXCHANGE:" in sent
    assert "- ASKED: Walk me through a recent computer vision project." in sent
    assert "mAP@50 and mAP@95" in sent
    # The current turn still reads last, so the answer being scored is unambiguous.
    assert sent.index("EARLIER_IN_THIS_EXCHANGE:") < sent.index("ANSWER:")
    assert sent.rstrip().endswith(FOLLOW_UP_ANSWER)


@pytest.mark.asyncio
async def test_a_main_question_sends_no_exchange_block():
    llm = RecordingLLMClient()

    await AnswerEvaluationService(llm=llm).evaluate(
        question_text="Walk me through a recent computer vision project.",
        category="technology",
        target="Computer Vision",
        answer=MAIN_ANSWER,
    )

    assert "EARLIER_IN_THIS_EXCHANGE" not in llm.inputs[0]
    assert llm.inputs[0].splitlines()[0].startswith("QUESTION:")


@pytest.mark.asyncio
async def test_other_targets_are_not_sent_as_exchange_context():
    """Cross-target hints and prior-exchange context are different things and stay apart."""
    llm = RecordingLLMClient()

    await AnswerEvaluationService(llm=llm).evaluate(
        question_text="And the results?",
        category="technology",
        target="Computer Vision",
        answer=FOLLOW_UP_ANSWER,
        other_targets=[("technology", "Kubernetes")],
        prior_exchange=[("Walk me through a project.", MAIN_ANSWER)],
    )

    sent = llm.inputs[0]
    exchange = sent[sent.index("EARLIER_IN_THIS_EXCHANGE:") : sent.index("OTHER_TARGETS:")]
    assert "Kubernetes" not in exchange
    assert "mAP@50" in exchange


def test_the_prompt_forbids_calling_established_facts_missing():
    """The instruction the model acts on, pinned in the prompt the service loads."""
    prompt = load_prompt("answer_evaluation", "v1")

    assert "EARLIER_IN_THIS_EXCHANGE" in prompt
    assert "Never record a weakness saying something is missing when the earlier block already" in (
        prompt
    )


# --- through the real graph --------------------------------------------------------------------


def _plan() -> InterviewPlan:
    return InterviewPlan(
        job_id="job-1",
        role_title="AI Engineer",
        occupation_match=OccupationMatch(
            onet_soc_code="15-2051.00", title="Data Scientists", score=0.2
        ),
        coverage_targets=[
            CoverageTarget(
                id="cv",
                category=QuestionCategory.TECHNOLOGY,
                target="Computer Vision",
                requirement_level=RequirementLevel.REQUIRED,
                source=EvidenceSource.JOBSPEC,
                priority=0,
                grounding="Job description requirement",
            ),
            CoverageTarget(
                id="k8s",
                category=QuestionCategory.TECHNOLOGY,
                target="Kubernetes",
                requirement_level=RequirementLevel.PREFERRED,
                source=EvidenceSource.JOBSPEC,
                priority=1,
                grounding="Job description requirement",
            ),
        ],
    )


def _graph(llm):
    return build_interview_graph(
        question_service=QuestionGenerationService(llm=FakeLLMClient()),
        evaluator=AnswerEvaluationService(llm=llm),
    )


@pytest.mark.asyncio
async def test_the_graph_hands_the_follow_up_its_own_exchange_and_nothing_else():
    """The one that would have caught the production defect."""
    follow_up_first = AnswerEvaluation(
        score=0.4,
        evidence_type=AnswerEvidenceType.PARTIAL,
        decision=EvaluationDecision.FOLLOW_UP,
        strengths=["Named the metrics used."],
        weaknesses=["No measured values were given."],
        evidence=["mAP@50 and mAP@95"],
        follow_up_needed=True,
        follow_up_question="Can you share the measured values?",
    )
    llm = RecordingLLMClient(evaluation=follow_up_first)
    graph = _graph(llm)
    config = {"configurable": {"thread_id": "exchange-context"}}

    await graph.ainvoke(build_graph_state(_plan()), config=config)
    await graph.ainvoke(Command(resume=MAIN_ANSWER), config=config)

    # Main question: no exchange block at all.
    assert "EARLIER_IN_THIS_EXCHANGE" not in llm.inputs[0]

    # It followed up, so the next evaluation must carry the main turn.
    llm._evaluation = llm._evaluation.model_copy(
        update={"decision": EvaluationDecision.ADVANCE, "follow_up_needed": False}
    )
    await graph.ainvoke(Command(resume=FOLLOW_UP_ANSWER), config=config)

    follow_up_input = llm.inputs[1]
    assert "EARLIER_IN_THIS_EXCHANGE:" in follow_up_input
    assert MAIN_ANSWER in follow_up_input
    # Strictly this target's exchange: the other coverage target's name appears only where the
    # cross-target hint list puts it, never inside the exchange block.
    exchange = follow_up_input[
        follow_up_input.index("EARLIER_IN_THIS_EXCHANGE:") : follow_up_input.index("ANSWER:")
    ]
    assert "Kubernetes" not in exchange.split("OTHER_TARGETS:")[0]


@pytest.mark.asyncio
async def test_the_fake_client_still_classifies_the_current_answer_with_context_present():
    """The fake reads the current ANSWER only; an exchange block above it must not confuse it."""
    service = AnswerEvaluationService(llm=FakeLLMClient())

    without = await service.evaluate(
        question_text="And the results?",
        category="technology",
        target="Computer Vision",
        answer=FOLLOW_UP_ANSWER,
    )
    with_context = await service.evaluate(
        question_text="And the results?",
        category="technology",
        target="Computer Vision",
        answer=FOLLOW_UP_ANSWER,
        prior_exchange=[("Walk me through a project.", MAIN_ANSWER)],
    )

    assert with_context.evidence_type == without.evidence_type
    assert with_context.score == without.score
