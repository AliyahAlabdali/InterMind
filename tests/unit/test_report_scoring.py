import pytest

from app.domain.evaluation import EvaluationDecision
from app.domain.interview import InterviewState, InterviewStatus
from app.domain.interview_plan import (
    CoverageTarget,
    EvidenceSource,
    InterviewPlan,
    QuestionCategory,
    RequirementLevel,
)
from app.domain.occupation import OccupationMatch
from app.domain.report import CompetencyAssessment, EvidenceStrength, Recommendation
from app.services.cross_target_evidence import resolve_cross_target_evidence
from app.services.report_scoring import (
    build_areas_to_explore,
    build_competency_assessments,
    build_question_evaluations,
    build_strengths,
    build_unassessed_required_targets,
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


def _plan(coverage_targets: list[CoverageTarget]) -> InterviewPlan:
    return InterviewPlan(
        job_id="job-1",
        role_title="Software Developer",
        occupation_match=OccupationMatch(
            onet_soc_code="15-1252.00", title="Software Developers", score=1.0
        ),
        coverage_targets=coverage_targets,
    )


def _question(qid: str, category: QuestionCategory, target: str) -> CoverageTarget:
    return CoverageTarget(
        id=qid,
        category=category,
        target=target,
        requirement_level=RequirementLevel.REQUIRED,
        source=EvidenceSource.JOBSPEC,
        priority=0,
        grounding="g",
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


def test_cross_target_resolved_evidence_appears_in_the_report():
    """Real gap found after cross-target evidence shipped (see
    app.services.cross_target_evidence): a target resolved purely from evidence volunteered
    while answering a *different* question gets its own history entry, but its id was never
    added to `asked_question_ids` - only to `assessed_target_ids` (correctly stopping the live
    interview from re-asking about it). Iterating `asked_question_ids` here silently dropped
    that target from the report entirely, even though real, correctly-classified evidence for
    it existed. This is the regression test for the fix: iterate history (via
    `root_question_id`), not `asked_question_ids`.
    """
    plan = _plan(
        [
            _question("python", QuestionCategory.TECHNOLOGY, "Python"),
            _question("postgres", QuestionCategory.TECHNOLOGY, "PostgreSQL"),
        ]
    )
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        # Only "python" was ever asked directly - "postgres" was resolved purely via
        # cross-target evidence and was deliberately never appended here (see
        # app.agents.interview_graph.evaluate_answer).
        asked_question_ids=["python"],
        history=[
            {
                "question_id": "python",
                "question": "Tell me about Python.",
                "answer": "I used Python with FastAPI. For persistence I used PostgreSQL.",
                "evaluation": _evaluation(0.8, "advance", strengths=["Built a FastAPI service"]),
            },
            {
                "question_id": "postgres",
                "question": (
                    "(Not asked directly - identified from the candidate's answer to a "
                    "different question.)"
                ),
                "answer": "For persistence I used PostgreSQL.",
                "evaluation": {
                    "score": 0.8,
                    "decision": "advance",
                    "evidence_type": "demonstrated",
                    "strengths": ["Volunteered relevant experience with PostgreSQL."],
                    "weaknesses": [],
                    "evidence": ["For persistence I used PostgreSQL."],
                    "follow_up_needed": False,
                    "follow_up_question": None,
                },
                "root_question_id": "postgres",
            },
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    targets = {e.target for e in evaluations}
    assert targets == {"Python", "PostgreSQL"}

    postgres_eval = next(e for e in evaluations if e.target == "PostgreSQL")
    assert postgres_eval.score == 0.8
    assert postgres_eval.evidence_type.value == "demonstrated"

    # It also flows into the competency assessments and overall score - not just the raw
    # per-question list.
    competencies = build_competency_assessments(evaluations)
    assert {c.name for c in competencies} == {"Python", "PostgreSQL"}
    assert compute_overall_score(competencies) == pytest.approx(0.8)


# --- build_unassessed_required_targets: report-consistency review -------------------------


def test_assessed_required_target_with_strong_evidence_is_never_listed_as_unassessed():
    """Real-run finding: the report claimed 'the interview did not cover... designing database
    schemas in PostgreSQL' while the report's own PostgreSQL assessment showed strong,
    directly-questioned evidence. `unassessed_required_targets` must be derived from the exact
    same evaluated-id set `build_question_evaluations` produces, so a target that was actually
    assessed can never simultaneously appear here - there is no separate heuristic list that
    could disagree with the assessments."""
    plan = _plan(
        [
            _question("postgres", QuestionCategory.TECHNOLOGY, "PostgreSQL schema design"),
        ]
    )
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["postgres"],
        history=[
            {
                "question_id": "postgres",
                "question": (
                    "Can you describe your experience designing database schemas in "
                    "PostgreSQL for backend applications?"
                ),
                "answer": "detailed schema-design answer with normalization and indexing",
                "evaluation": _evaluation(
                    0.9, "advance", strengths=["Gave a detailed, concrete schema example"]
                ),
            }
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    unassessed = build_unassessed_required_targets(plan, evaluations)
    assert "PostgreSQL schema design" not in unassessed
    assert unassessed == []


def test_required_target_with_no_assessment_at_all_is_listed_as_unassessed():
    plan = _plan(
        [
            _question("python", QuestionCategory.TECHNOLOGY, "Python"),
            _question("git", QuestionCategory.TECHNOLOGY, "Git"),
        ]
    )
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["python"],
        history=[
            {
                "question_id": "python",
                "question": "Q?",
                "answer": "a",
                "evaluation": _evaluation(0.9, "advance"),
            }
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    unassessed = build_unassessed_required_targets(plan, evaluations)
    assert unassessed == ["Git"]


def test_assessed_and_unassessed_lists_can_never_contain_the_same_target():
    """Report-consistency regression (item 10): reproduces the real-run shape - some required
    targets strongly assessed, two (Git, ML model integration) never reached at all - and
    asserts the assessed-competency names and the unassessed-required-targets names are always
    disjoint, however the interview actually played out."""
    plan = _plan(
        [
            _question("python", QuestionCategory.TECHNOLOGY, "Python"),
            _question("postgres", QuestionCategory.TECHNOLOGY, "PostgreSQL"),
            _question("git", QuestionCategory.TECHNOLOGY, "Git"),
            _question("ml", QuestionCategory.COMPETENCY, "ML model integration"),
        ]
    )
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["python", "postgres"],
        history=[
            {
                "question_id": "python",
                "question": "Q?",
                "answer": "a",
                "evaluation": _evaluation(0.9, "advance"),
            },
            {
                "question_id": "postgres",
                "question": "Q?",
                "answer": "a",
                "evaluation": _evaluation(0.85, "advance"),
            },
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    competencies = build_competency_assessments(evaluations)
    unassessed = build_unassessed_required_targets(plan, evaluations)

    assessed_names = {c.name for c in competencies}
    assert assessed_names == {"Python", "PostgreSQL"}
    assert set(unassessed) == {"Git", "ML model integration"}
    assert assessed_names.isdisjoint(unassessed)


def test_cross_target_assessed_required_target_is_not_listed_as_unassessed():
    """Item 9.2 (final backend pass): a required target resolved purely via cross-target
    evidence - never asked directly - must not appear in unassessed_required_targets, and must
    carry assessment_method="cross_target" so the report can still distinguish it from a
    directly-asked question. Uses the real `resolve_cross_target_evidence` function, not a
    hand-built history entry, so this also exercises the actual production wiring."""
    plan = _plan(
        [
            _question("python", QuestionCategory.TECHNOLOGY, "Python"),
            _question("postgres", QuestionCategory.TECHNOLOGY, "PostgreSQL"),
        ]
    )
    coverage_targets = [
        {
            "id": "python",
            "target": "Python",
            "category": "technology",
            "requirement_level": "required",
            "priority": 0,
            "grounding": "g",
        },
        {
            "id": "postgres",
            "target": "PostgreSQL",
            "category": "technology",
            "requirement_level": "required",
            "priority": 1,
            "grounding": "g",
        },
    ]
    resolution = resolve_cross_target_evidence(
        coverage_targets=coverage_targets,
        current_target_id="python",
        assessed_target_ids=[],
        cross_target_evidence=[
            {
                "target": "PostgreSQL",
                "evidence_type": "demonstrated",
                "note": "I used PostgreSQL with normalized schemas.",
            }
        ],
        existing_hints={},
    )
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["python"],
        history=[
            {
                "question_id": "python",
                "question": "Tell me about Python.",
                "answer": "I used Python. I used PostgreSQL with normalized schemas.",
                "evaluation": _evaluation(0.9, "advance"),
            },
            *resolution.history_entries,
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    unassessed = build_unassessed_required_targets(plan, evaluations)
    assert "PostgreSQL" not in unassessed

    postgres_eval = next(e for e in evaluations if e.target == "PostgreSQL")
    assert postgres_eval.assessment_method == "cross_target"

    competencies = {c.name: c for c in build_competency_assessments(evaluations)}
    assert competencies["PostgreSQL"].assessment_method == "cross_target"
    assert competencies["Python"].assessment_method == "direct"


def test_non_conclusive_cross_target_evidence_does_not_mark_the_target_assessed():
    """Item 9.3: "related evidence" (a casual/claimed-unverified mention of a different
    target) must remain a hint only - never enough on its own to resolve that target - so if
    the interview ends without ever asking about it directly, it correctly still shows up as
    unassessed rather than being silently promoted to "assessed"."""
    plan = _plan(
        [
            _question("python", QuestionCategory.TECHNOLOGY, "Python"),
            _question("git", QuestionCategory.TECHNOLOGY, "Git"),
        ]
    )
    coverage_targets = [
        {
            "id": "python",
            "target": "Python",
            "category": "technology",
            "requirement_level": "required",
            "priority": 0,
            "grounding": "g",
        },
        {
            "id": "git",
            "target": "Git",
            "category": "technology",
            "requirement_level": "required",
            "priority": 1,
            "grounding": "g",
        },
    ]
    resolution = resolve_cross_target_evidence(
        coverage_targets=coverage_targets,
        current_target_id="python",
        assessed_target_ids=[],
        cross_target_evidence=[
            {
                "target": "Git",
                "evidence_type": "claimed_unverified",
                "note": "we used some version control",
            }
        ],
        existing_hints={},
    )
    assert resolution.newly_assessed_ids == []
    assert resolution.history_entries == []
    assert "git" in resolution.updated_hints

    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["python"],
        history=[
            {
                "question_id": "python",
                "question": "Tell me about Python.",
                "answer": "I used Python. we used some version control",
                "evaluation": _evaluation(0.9, "advance"),
            }
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    unassessed = build_unassessed_required_targets(plan, evaluations)
    assert unassessed == ["Git"]


def test_explicit_lack_is_distinguishable_from_not_assessed_in_the_same_report():
    """Item 9.4: a target the candidate explicitly denied experience with is DIFFERENT from a
    target the interview never reached at all - the former was assessed (has evidence showing
    a lack), the latter has no evidence of any kind. Both must be individually correct in the
    same report."""
    plan = _plan(
        [
            _question("python", QuestionCategory.TECHNOLOGY, "Python"),
            _question("git", QuestionCategory.TECHNOLOGY, "Git"),
        ]
    )
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["python"],
        history=[
            {
                "question_id": "python",
                "question": "Q?",
                "answer": "I have never used Python.",
                "evaluation": _evaluation_with_type(0.05, "advance", "explicit_lack"),
            }
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    competencies = {c.name: c for c in build_competency_assessments(evaluations)}
    unassessed = build_unassessed_required_targets(plan, evaluations)

    assert competencies["Python"].evidence_label == "No evidence"  # explicit lack - assessed
    assert "Python" not in unassessed
    assert unassessed == ["Git"]  # never touched at all - a different claim entirely


def test_scoring_is_unaffected_by_unassessed_required_targets():
    """Scoring semantics (item 8): the score reflects only the evidence actually gathered - a
    required target the interview never reached must not lower the score, since that would
    silently conflate "the adaptive interview ended before asking" with "the candidate failed
    it". Strong evidence on the assessed targets must produce the same score whether or not
    other required targets remain unassessed."""
    plan_with_gap = _plan(
        [
            _question("python", QuestionCategory.TECHNOLOGY, "Python"),
            _question("git", QuestionCategory.TECHNOLOGY, "Git"),
        ]
    )
    plan_fully_covered = _plan([_question("python", QuestionCategory.TECHNOLOGY, "Python")])
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["python"],
        history=[
            {
                "question_id": "python",
                "question": "Q?",
                "answer": "a",
                "evaluation": _evaluation(0.95, "advance"),
            }
        ],
    )
    evaluations = build_question_evaluations(plan_with_gap, state)
    competencies = build_competency_assessments(evaluations)
    score_with_gap = compute_overall_score(competencies)
    unassessed = build_unassessed_required_targets(plan_with_gap, evaluations)

    evaluations_full = build_question_evaluations(plan_fully_covered, state)
    competencies_full = build_competency_assessments(evaluations_full)
    score_fully_covered = compute_overall_score(competencies_full)

    assert unassessed == ["Git"]
    assert score_with_gap == pytest.approx(score_fully_covered)
    assert score_with_gap == pytest.approx(0.95)
    assert derive_recommendation(score_with_gap) == Recommendation.STRONG_HIRE


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


# --- evidence_type / evidence_label: distinct low-evidence reasons render distinct labels ----
#
# Report-review fix: "explicitly stated no experience" and "claimed experience but couldn't
# verify it" both land in the same INSUFFICIENT `evidence_strength` band (score-only), but must
# render as different, accurate labels - "No evidence" vs "Insufficient evidence" - rather than
# one generic phrase. See app.domain.evaluation.evidence_label.


def _evaluation_with_type(score: float, decision: str, evidence_type: str) -> dict:
    return {
        "score": score,
        "decision": decision,
        "evidence_type": evidence_type,
        "strengths": [],
        "weaknesses": ["some recorded gap"],
        "evidence": [],
        "follow_up_needed": decision == "follow_up",
        "follow_up_question": None,
    }


def test_explicit_lack_and_claimed_unverified_render_different_evidence_labels():
    plan = _plan(
        [
            _question("q1", QuestionCategory.TECHNOLOGY, "Python"),
            _question("q2", QuestionCategory.TECHNOLOGY, "Java"),
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
                "answer": "I don't have projects with Python.",
                "evaluation": _evaluation_with_type(0.05, "advance", "explicit_lack"),
            },
            {
                "question_id": "q2",
                "question": "Q2?",
                "answer": "I don't remember, but I used MATLAB and C++.",
                "evaluation": _evaluation_with_type(0.15, "follow_up", "claimed_unverified"),
            },
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    by_target = {e.target: e for e in evaluations}

    assert by_target["Python"].evidence_label == "No evidence"
    assert by_target["Java"].evidence_label == "Unverified claim"
    assert by_target["Python"].evidence_label != by_target["Java"].evidence_label

    competencies = {c.name: c for c in build_competency_assessments(evaluations)}
    assert competencies["Python"].evidence_label == "No evidence"
    assert competencies["Java"].evidence_label == "Unverified claim"


def test_evidence_label_is_not_assessed_for_a_blank_turn():
    plan = _plan([_question("q1", QuestionCategory.COMPETENCY, "Ownership")])
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["q1"],
        history=[{"question_id": "q1", "question": "Q1?", "answer": "", "evaluation": None}],
    )
    evaluations = build_question_evaluations(plan, state)
    assert evaluations[0].evidence_type is None
    assert evaluations[0].evidence_label == "Not assessed"


def test_evidence_type_missing_from_legacy_history_dict_does_not_error():
    """A hand-built/legacy evaluation dict without `evidence_type` (predates this field) must
    still work - treated as unknown, never a KeyError."""
    plan = _plan([_question("q1", QuestionCategory.COMPETENCY, "Ownership")])
    state = InterviewState(
        job_id="job-1",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["q1"],
        history=[
            {
                "question_id": "q1",
                "question": "Q1?",
                "answer": "a",
                "evaluation": _evaluation(0.8, "advance"),
            }
        ],
    )
    evaluations = build_question_evaluations(plan, state)
    assert evaluations[0].evidence_type is None
    assert evaluations[0].evidence_label == "Not assessed"


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
