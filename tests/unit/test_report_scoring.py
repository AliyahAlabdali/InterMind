import pytest

from app.domain.evaluation import EvaluationDecision
from app.domain.interview import InterviewState, InterviewStatus
from app.domain.interview_plan import (
    InterviewPlan,
    InterviewQuestion,
    QuestionCategory,
)
from app.domain.occupation import OccupationMatch
from app.domain.report import CompetencyAssessment, EvidenceStrength, Recommendation
from app.services.report_scoring import (
    build_areas_to_explore,
    build_competency_assessments,
    build_question_evaluations,
    build_strengths,
    compute_overall_score,
    derive_recommendation,
    evidence_strength_for_score,
)


def _evaluation(
    score: float, decision: str, *, strengths=None, weaknesses=None, evidence=None
) -> dict:
    return {
        "score": score,
        "decision": decision,
        "strengths": strengths or [],
        "weaknesses": weaknesses or [],
        "evidence": evidence or [f"evidence for score {score}"],
        "follow_up_needed": decision == "follow_up",
        "follow_up_question": None,
    }


def _plan(questions: list[InterviewQuestion]) -> InterviewPlan:
    return InterviewPlan(
        job_id="job-1",
        occupation_match=OccupationMatch(
            onet_soc_code="15-1252.00", title="Software Developers", score=1.0
        ),
        questions=questions,
    )


def _question(qid: str, category: QuestionCategory, target: str) -> InterviewQuestion:
    return InterviewQuestion(
        id=qid, category=category, text=f"Question about {target}?", target=target, grounding="g"
    )


# --- build_question_evaluations -----------------------------------------------------------


def test_last_turn_wins_for_a_followed_up_question():
    plan = _plan([_question("q1", QuestionCategory.COMPETENCY, "Ownership")])
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["q1"],
        history=[
            {
                "question_id": "q1",
                "question": "Question about Ownership?",
                "answer": "short",
                "evaluation": _evaluation(0.3, "follow_up", weaknesses=["too short"]),
            },
            {
                "question_id": "q1",
                "question": "Question about Ownership?",
                "answer": "a much more detailed answer with a concrete example",
                "evaluation": _evaluation(0.8, "advance", strengths=["concrete example"]),
            },
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    assert len(evaluations) == 1
    assert evaluations[0].score == 0.8
    assert evaluations[0].decision == EvaluationDecision.ADVANCE
    assert evaluations[0].candidate_answer == "a much more detailed answer with a concrete example"
    assert evaluations[0].strengths == ["concrete example"]


def test_order_follows_asked_question_ids():
    plan = _plan(
        [
            _question("q1", QuestionCategory.COMPETENCY, "A"),
            _question("q2", QuestionCategory.TECHNOLOGY, "B"),
        ]
    )
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["q2", "q1"],
        history=[
            {
                "question_id": "q2",
                "question": "Q2?",
                "answer": "ans2",
                "evaluation": _evaluation(0.5, "advance"),
            },
            {
                "question_id": "q1",
                "question": "Q1?",
                "answer": "ans1",
                "evaluation": _evaluation(0.9, "advance"),
            },
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    assert [e.question_id for e in evaluations] == ["q2", "q1"]


def test_blank_answer_with_no_evaluation_is_none_not_guessed():
    plan = _plan([_question("q1", QuestionCategory.COMPETENCY, "Ownership")])
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["q1"],
        history=[
            {"question_id": "q1", "question": "Q1?", "answer": "", "evaluation": None},
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    assert evaluations[0].score is None
    assert evaluations[0].decision is None
    assert evaluations[0].evidence == []
    assert evaluations[0].strengths == []


# --- build_competency_assessments ----------------------------------------------------------


def test_competency_score_is_mean_of_its_questions():
    plan = _plan(
        [
            _question("q1", QuestionCategory.TECHNOLOGY, "Python"),
            _question("q2", QuestionCategory.TECHNOLOGY, "Python"),
        ]
    )
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["q1", "q2"],
        history=[
            {
                "question_id": "q1",
                "question": "Q1?",
                "answer": "a1",
                "evaluation": _evaluation(0.6, "advance", strengths=["s1"], evidence=["e1"]),
            },
            {
                "question_id": "q2",
                "question": "Q2?",
                "answer": "a2",
                "evaluation": _evaluation(1.0, "advance", strengths=["s2"], evidence=["e2"]),
            },
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    competencies = build_competency_assessments(evaluations)
    assert len(competencies) == 1
    assert competencies[0].name == "Python"
    assert competencies[0].score == 0.8
    assert competencies[0].strengths == ["s1", "s2"]
    assert competencies[0].evidence == ["e1", "e2"]


def test_competency_with_no_scored_questions_has_none_score():
    plan = _plan([_question("q1", QuestionCategory.COMPETENCY, "Ownership")])
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["q1"],
        history=[{"question_id": "q1", "question": "Q1?", "answer": "", "evaluation": None}],
    )
    evaluations = build_question_evaluations(plan, state)
    competencies = build_competency_assessments(evaluations)
    assert competencies[0].score is None


def test_competency_grouping_deterministic_across_repeated_calls():
    plan = _plan(
        [
            _question("q1", QuestionCategory.COMPETENCY, "A"),
            _question("q2", QuestionCategory.TECHNOLOGY, "B"),
        ]
    )
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["q1", "q2"],
        history=[
            {
                "question_id": "q1",
                "question": "Q1?",
                "answer": "a1",
                "evaluation": _evaluation(0.5, "advance"),
            },
            {
                "question_id": "q2",
                "question": "Q2?",
                "answer": "a2",
                "evaluation": _evaluation(0.7, "advance"),
            },
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    first = build_competency_assessments(evaluations)
    second = build_competency_assessments(evaluations)
    assert first == second


# --- compute_overall_score ------------------------------------------------------------------


def test_overall_score_weights_categories_not_flat_average():
    plan = _plan(
        [
            _question("q1", QuestionCategory.COMPETENCY, "A"),
            _question("q2", QuestionCategory.COMPETENCY, "B"),
            _question("q3", QuestionCategory.COMPETENCY, "C"),
            _question("q4", QuestionCategory.COMPETENCY, "D"),
            _question("q5", QuestionCategory.TECHNOLOGY, "E"),
            _question("q6", QuestionCategory.TASK, "F"),
        ]
    )
    # competency avg = (0.3 + 0.8 + 0.8 + 0.8) / 4 = 0.675, technology = 0.8, task = 0.8
    scores = {"q1": 0.3, "q2": 0.8, "q3": 0.8, "q4": 0.8, "q5": 0.8, "q6": 0.8}
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=list(scores),
        history=[
            {
                "question_id": qid,
                "question": "Q?",
                "answer": "a",
                "evaluation": _evaluation(score, "advance"),
            }
            for qid, score in scores.items()
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    competencies = build_competency_assessments(evaluations)
    overall = compute_overall_score(competencies)
    # 0.675*0.4 + 0.8*0.4 + 0.8*0.2 = 0.27 + 0.32 + 0.16 = 0.75
    assert overall == pytest.approx(0.75)

    # Flat (unweighted) average of the six raw scores would be a different number
    # (0.3+0.8*5)/6 = 0.71666...; confirms this isn't just averaging every raw score.
    flat_average = sum(scores.values()) / len(scores)
    assert overall != pytest.approx(flat_average)


def test_overall_score_renormalizes_over_present_categories_only():
    plan = _plan([_question("q1", QuestionCategory.TASK, "F")])
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["q1"],
        history=[
            {
                "question_id": "q1",
                "question": "Q?",
                "answer": "a",
                "evaluation": _evaluation(0.9, "advance"),
            }
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    competencies = build_competency_assessments(evaluations)
    # Only "task" is present; its weight (0.2) is renormalised to 1.0, so the overall score
    # equals the task average exactly, not 0.9 * 0.2.
    assert compute_overall_score(competencies) == pytest.approx(0.9)


def test_overall_score_is_zero_when_nothing_was_scored():
    plan = _plan([_question("q1", QuestionCategory.COMPETENCY, "A")])
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["q1"],
        history=[{"question_id": "q1", "question": "Q?", "answer": "", "evaluation": None}],
    )
    evaluations = build_question_evaluations(plan, state)
    competencies = build_competency_assessments(evaluations)
    assert compute_overall_score(competencies) == 0.0


def test_overall_score_deterministic_across_repeated_calls():
    plan = _plan([_question("q1", QuestionCategory.COMPETENCY, "A")])
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["q1"],
        history=[
            {
                "question_id": "q1",
                "question": "Q?",
                "answer": "a",
                "evaluation": _evaluation(0.55, "advance"),
            }
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    competencies = build_competency_assessments(evaluations)
    assert compute_overall_score(competencies) == compute_overall_score(competencies)


# --- derive_recommendation -------------------------------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (1.0, Recommendation.STRONG_HIRE),
        (0.85, Recommendation.STRONG_HIRE),
        (0.849, Recommendation.HIRE),
        (0.65, Recommendation.HIRE),
        (0.649, Recommendation.CONSIDER),
        (0.45, Recommendation.CONSIDER),
        (0.449, Recommendation.NO_HIRE),
        (0.0, Recommendation.NO_HIRE),
    ],
)
def test_recommendation_thresholds(score, expected):
    assert derive_recommendation(score) == expected


# --- evidence_strength_for_score / EvidenceStrength -----------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (None, EvidenceStrength.NOT_ASSESSED),
        (0.0, EvidenceStrength.INSUFFICIENT),
        (0.3, EvidenceStrength.INSUFFICIENT),
        (0.34, EvidenceStrength.INSUFFICIENT),
        (0.35, EvidenceStrength.LIMITED),
        (0.59, EvidenceStrength.LIMITED),
        (0.6, EvidenceStrength.MODERATE),
        (0.79, EvidenceStrength.MODERATE),
        (0.8, EvidenceStrength.STRONG),
        (1.0, EvidenceStrength.STRONG),
    ],
)
def test_evidence_strength_bands(score, expected):
    assert evidence_strength_for_score(score) == expected


def test_a_low_effort_non_substantive_answer_reads_as_insufficient_not_a_deficiency():
    """A dismissive answer like "IDK" scores low (no real evidence either way), and must be
    represented as insufficient evidence - not as proof the candidate lacks the competency.
    """
    plan = _plan([_question("q1", QuestionCategory.COMPETENCY, "Leadership")])
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["q1"],
        history=[
            {
                "question_id": "q1",
                "question": "Q1?",
                "answer": "IDK",
                "evaluation": _evaluation(
                    0.1,
                    "follow_up",
                    weaknesses=["The answer was too brief to assess leadership."],
                ),
            }
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    competencies = build_competency_assessments(evaluations)
    assert evaluations[0].evidence_strength == EvidenceStrength.INSUFFICIENT
    assert competencies[0].evidence_strength == EvidenceStrength.INSUFFICIENT


def test_evidence_strength_is_computed_and_cannot_drift_from_score():
    """`evidence_strength` is a computed field, not an independently-settable one - so it is
    always consistent with `score`, regardless of what a caller constructing the model directly
    might otherwise pass."""
    assessment = CompetencyAssessment(name="X", category=QuestionCategory.COMPETENCY, score=0.9)
    assert assessment.evidence_strength == EvidenceStrength.STRONG


# --- build_strengths / build_areas_to_explore -----------------------------------------------


def _assessment(name: str, score: float | None, *, strengths=None, weaknesses=None):
    return CompetencyAssessment(
        name=name,
        category=QuestionCategory.COMPETENCY,
        score=score,
        strengths=strengths or [],
        weaknesses=weaknesses or [],
    )


def test_areas_to_explore_does_not_repeat_identical_text_across_items():
    """Regression test: the old report showed the same boilerplate weakness sentence for every
    item, differing only by an interpolated name. Each note here must be distinct and clearly
    tied to its own competency."""
    competencies = [
        _assessment("Leadership", 0.1, weaknesses=["No concrete example was given."]),
        _assessment("Collaboration", 0.1, weaknesses=["No concrete example was given."]),
    ]
    notes = build_areas_to_explore(competencies)
    assert len(notes) == len(set(notes))  # every note is unique text
    assert notes[0].startswith("Leadership:") or notes[0].startswith("Collaboration:")
    assert all(":" in note for note in notes)  # each note names its own competency


def test_areas_to_explore_synthesizes_an_honest_note_for_insufficient_evidence_with_no_weakness():
    """A competency with insufficient evidence but no recorded weakness text (e.g. a blank
    turn) still gets a plain, honest note - never a fabricated critique."""
    competencies = [_assessment("Leadership", None, weaknesses=[])]
    notes = build_areas_to_explore(competencies)
    assert len(notes) == 1
    assert notes[0].startswith("Leadership:")
    assert "no conclusive evidence" in notes[0].lower()


def test_areas_to_explore_ranks_weakest_evidence_first():
    competencies = [
        _assessment("Strong Area", 0.9, weaknesses=["minor nitpick"]),
        _assessment("Weak Area", 0.1, weaknesses=["barely addressed"]),
    ]
    notes = build_areas_to_explore(competencies)
    assert notes[0].startswith("Weak Area:")


def test_strengths_never_invents_one_for_a_competency_with_none_recorded():
    competencies = [
        _assessment("Has Strength", 0.9, strengths=["Gave a concrete example"]),
        _assessment("No Strength", 0.9, strengths=[]),
    ]
    notes = build_strengths(competencies)
    assert notes == ["Has Strength: Gave a concrete example"]
