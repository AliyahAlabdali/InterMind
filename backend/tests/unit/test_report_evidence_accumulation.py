"""Evidence established in a main answer must survive the follow-up that came after it.

From a real interview: the main answer named the evaluation metrics used (mAP@50, mAP@95), the
follow-up then described the implementation, and the report said the candidate had given no
specific evaluation metrics. ``build_question_evaluations`` kept only the last turn, so the
earlier turn's evidence never reached the Evidence section or the narrative prompt - while the
interview record, which reads the raw history, still showed the candidate naming them.

These pin both halves of the contract: what accumulates across an exchange (evidence, strengths)
and what stays the last turn's alone (score, decision, evidence type, identity, weaknesses).
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.domain.evaluation import AnswerEvidenceType, EvaluationDecision
from app.domain.interview import InterviewState, InterviewStatus
from app.domain.interview_plan import (
    CoverageTarget,
    EvidenceSource,
    InterviewPlan,
    QuestionCategory,
    RequirementLevel,
)
from app.domain.occupation import OccupationMatch
from app.domain.report import ReportNarrative
from app.services.report_narrative import ReportNarrativeService
from app.services.report_scoring import (
    build_competency_assessments,
    build_question_evaluations,
    compute_overall_score,
)

TARGET_ID = "cv"


def _plan() -> InterviewPlan:
    return InterviewPlan(
        job_id="job-1",
        role_title="AI Engineer",
        occupation_match=OccupationMatch(
            onet_soc_code="15-2051.00", title="Data Scientists", score=0.14
        ),
        coverage_targets=[
            CoverageTarget(
                id=TARGET_ID,
                category=QuestionCategory.TECHNOLOGY,
                target="Computer Vision",
                requirement_level=RequirementLevel.REQUIRED,
                source=EvidenceSource.JOBSPEC,
                priority=0,
                grounding="Job description requirement",
            )
        ],
    )


def _turn(
    *,
    question_id: str,
    question: str,
    answer: str,
    evaluation: dict | None,
) -> dict:
    return {
        "question_id": question_id,
        "question": question,
        "answer": answer,
        "evaluation": evaluation,
        "root_question_id": TARGET_ID,
    }


def _evaluation(
    *,
    score: float,
    decision: str,
    evidence_type: str,
    evidence: list[str],
    strengths: list[str],
    weaknesses: list[str],
) -> dict:
    return {
        "score": score,
        "decision": decision,
        "evidence_type": evidence_type,
        "evidence": evidence,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "follow_up_needed": decision == "follow_up",
        "follow_up_question": None,
    }


# The production shape: metrics named in the main answer, implementation in the follow-up.
MAIN = _turn(
    question_id=TARGET_ID,
    question="Can you walk me through a recent computer vision project?",
    answer="We applied YOLO and evaluated it with mAP@50 and mAP@95.",
    evaluation=_evaluation(
        score=0.55,
        decision="follow_up",
        evidence_type="partial",
        evidence=["We applied a computer vision model, which is YOLO", "mAP@50 and mAP@95"],
        strengths=["Named the model family and the evaluation metrics used."],
        weaknesses=["No measured values were given for the metrics named."],
    ),
)

FOLLOW_UP = _turn(
    question_id="followup-cv-0",
    question="Can you explain how you implemented the model and share some results?",
    answer="I trained it with transfer learning and saw a 2X to 3X improvement.",
    evaluation=_evaluation(
        score=0.45,
        decision="advance",
        evidence_type="partial",
        evidence=[
            "trained the model using a transfer learning approach",
            "evaluated it on unseen test sets containing videos and images",
            "approximately 2X to 3X improvement",
        ],
        strengths=["Described a transfer-learning approach and an unseen test set."],
        weaknesses=["No concrete numerical results were provided beyond the general statement."],
    ),
)


def _state(history: list[dict]) -> InterviewState:
    return InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=[TARGET_ID],
        history=history,
    )


# --- what accumulates ------------------------------------------------------------------------


def test_evidence_and_strengths_from_both_turns_survive_in_order():
    summaries = build_question_evaluations(_plan(), _state([MAIN, FOLLOW_UP]))

    assert len(summaries) == 1
    assert summaries[0].evidence == [
        "We applied a computer vision model, which is YOLO",
        "mAP@50 and mAP@95",
        "trained the model using a transfer learning approach",
        "evaluated it on unseen test sets containing videos and images",
        "approximately 2X to 3X improvement",
    ]
    assert summaries[0].strengths == [
        "Named the model family and the evaluation metrics used.",
        "Described a transfer-learning approach and an unseen test set.",
    ]


def test_evidence_repeated_across_turns_is_not_duplicated():
    repeated = _turn(
        question_id="followup-cv-0",
        question="And the metrics?",
        answer="mAP@50 and mAP@95, as I said.",
        evaluation=_evaluation(
            score=0.5,
            decision="advance",
            evidence_type="partial",
            evidence=["mAP@50 and mAP@95", "a second, new quote"],
            strengths=["Named the model family and the evaluation metrics used."],
            weaknesses=[],
        ),
    )
    summaries = build_question_evaluations(_plan(), _state([MAIN, repeated]))

    assert summaries[0].evidence == [
        "We applied a computer vision model, which is YOLO",
        "mAP@50 and mAP@95",
        "a second, new quote",
    ]
    assert summaries[0].strengths == ["Named the model family and the evaluation metrics used."]


def test_a_blank_turn_contributes_nothing_and_breaks_nothing():
    blank = _turn(question_id=TARGET_ID, question="Q?", answer="", evaluation=None)
    summaries = build_question_evaluations(_plan(), _state([blank, FOLLOW_UP]))

    assert summaries[0].evidence == FOLLOW_UP["evaluation"]["evidence"]
    assert summaries[0].score == 0.45


# --- what stays the last turn's --------------------------------------------------------------


def test_last_turn_remains_authoritative_for_the_outcome():
    summaries = build_question_evaluations(_plan(), _state([MAIN, FOLLOW_UP]))
    summary = summaries[0]

    # No averaging: 0.45, not the 0.5 mean of 0.55 and 0.45.
    assert summary.score == 0.45
    assert summary.decision is EvaluationDecision.ADVANCE
    assert summary.evidence_type is AnswerEvidenceType.PARTIAL
    assert summary.question_id == "followup-cv-0"
    assert summary.question == FOLLOW_UP["question"]
    assert summary.candidate_answer == FOLLOW_UP["answer"]
    assert summary.target_id == TARGET_ID


def test_scoring_is_unchanged_by_accumulation():
    competencies = build_competency_assessments(
        build_question_evaluations(_plan(), _state([MAIN, FOLLOW_UP]))
    )
    assert competencies[0].score == 0.45
    assert compute_overall_score(competencies) == 0.45


def test_gaps_are_the_last_turn_s_and_earlier_ones_do_not_reappear():
    summaries = build_question_evaluations(_plan(), _state([MAIN, FOLLOW_UP]))

    assert summaries[0].weaknesses == [
        "No concrete numerical results were provided beyond the general statement."
    ]
    # The main turn's gap was what the follow-up went on to probe, so it must not be reported
    # as still open.
    assert "No measured values were given for the metrics named." not in summaries[0].weaknesses


# --- through to the report input ---------------------------------------------------------------


def test_earlier_evidence_reaches_the_competency_assessment():
    competencies = build_competency_assessments(
        build_question_evaluations(_plan(), _state([MAIN, FOLLOW_UP]))
    )

    assert len(competencies) == 1
    assert "mAP@50 and mAP@95" in competencies[0].evidence
    assert "trained the model using a transfer learning approach" in competencies[0].evidence
    assert any("evaluation metrics" in s for s in competencies[0].strengths)


@pytest.mark.asyncio
async def test_earlier_evidence_reaches_the_narrative_prompt():
    """The narrative can only describe what it is handed - see ReportNarrativeService."""

    class RecordingLLMClient:
        def __init__(self) -> None:
            self.input_text = ""

        async def generate_structured(self, *, prompt, input_text, schema: type[BaseModel]):
            self.input_text = input_text
            return ReportNarrative(summary="ok", strengths=[], weaknesses=[])

    llm = RecordingLLMClient()
    competencies = build_competency_assessments(
        build_question_evaluations(_plan(), _state([MAIN, FOLLOW_UP]))
    )

    await ReportNarrativeService(llm=llm).synthesize(
        overall_score=0.45,
        recommendation="no_hire",
        competencies=competencies,
        unassessed_required_targets=[],
    )

    assert "mAP@50 and mAP@95" in llm.input_text
    assert "transfer learning" in llm.input_text
