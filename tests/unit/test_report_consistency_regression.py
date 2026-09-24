"""Regression tests for the report's "Required, never reached" inconsistency found in QA.

The symptom: a report simultaneously listed Docker under ``Strong evidence`` (asked, answered,
scored) and under ``Not established -> Required, never reached``. Distributed Systems did the
same with ``Partial evidence``. Both cannot be true.

Root cause: ``build_question_evaluations`` groups turns by ``root_question_id`` (correct), but
reported ``question_id=turn["question_id"]`` - which for a target whose LAST turn was a
follow-up is the *follow-up's* own generated id, not the coverage target's.
``build_unassessed_required_targets`` then matched those ids against ``plan.coverage_targets``
ids and found no match, so a fully-assessed target was reported as never reached.

The fix gives ``QuestionEvaluationSummary`` an explicit ``target_id`` - one consistent
definition of "which coverage target is this about" - and keys "reached" on that.

Scenario mirrors the real QA interview record: 10 questions asked, several of them
follow-up-terminated, with required targets left over because the interview hit its length
budget.
"""

from __future__ import annotations

from app.domain.interview import InterviewState, InterviewStatus
from app.domain.interview_plan import (
    CoverageTarget,
    EvidenceSource,
    InterviewPlan,
    QuestionCategory,
    RequirementLevel,
)
from app.domain.occupation import OccupationMatch
from app.domain.report import InterviewReport, Recommendation
from app.services.report_scoring import (
    build_question_evaluations,
    build_unassessed_required_targets,
)


def _evaluation(score: float, decision: str) -> dict:
    return {
        "score": score,
        "decision": decision,
        "strengths": [],
        "weaknesses": [],
        "evidence": [f"evidence at {score}"],
        "follow_up_needed": decision == "follow_up",
        "follow_up_question": None,
    }


def _target(
    id: str,
    name: str,
    *,
    category: QuestionCategory = QuestionCategory.TECHNOLOGY,
    level: RequirementLevel = RequirementLevel.REQUIRED,
) -> CoverageTarget:
    return CoverageTarget(
        id=id,
        category=category,
        target=name,
        requirement_level=level,
        source=EvidenceSource.JOBSPEC,
        priority=0,
        grounding="Job description requirement",
    )


#: The required plan from the QA scenario: some reached, some genuinely never touched.
PLAN = InterviewPlan(
    job_id="job-qa",
    role_title="Senior Backend Software Engineer",
    occupation_match=OccupationMatch(
        onet_soc_code="15-1252.00", title="Software Developers", score=1.0
    ),
    coverage_targets=[
        _target("docker", "Docker"),
        _target("distributed_systems", "Distributed Systems"),
        _target("java", "Java"),  # resolved only via cross-target evidence
        _target("kubernetes", "Kubernetes"),  # genuinely never reached
        _target("graphql", "GraphQL"),  # genuinely never reached
    ],
)


def _qa_state() -> InterviewState:
    """Docker ends on a follow-up (the shape that triggered the bug), Distributed Systems is
    partially evidenced, Java arrives only as cross-target evidence, and two required targets
    are never touched at all because the interview ran out of budget."""
    return InterviewState(
        job_id="job-qa",
        status=InterviewStatus.COMPLETED,
        asked_question_ids=["docker", "docker::fu::0", "distributed_systems"],
        history=[
            {
                "question_id": "docker",
                "question": "Tell me about Docker.",
                "answer": "We containerised our services.",
                "evaluation": _evaluation(0.55, "follow_up"),
                "root_question_id": "docker",
            },
            {
                # The follow-up's own id - this is what used to leak into the report as the
                # summary's `question_id` and break the "reached" match.
                "question_id": "docker::fu::0",
                "question": "How did you handle image layering and build caching?",
                "answer": "Multi-stage builds, cached the dependency layer separately.",
                "evaluation": _evaluation(0.85, "advance"),
                "root_question_id": "docker",
            },
            {
                "question_id": "distributed_systems",
                "question": "Tell me about Distributed Systems.",
                "answer": "I worked on a queue consumer but didn't design the topology.",
                "evaluation": _evaluation(0.45, "advance"),
                "root_question_id": "distributed_systems",
            },
            {
                # A cross-target resolution: never asked directly, still reached.
                "question_id": "java",
                "question": "Java (mentioned while answering another question)",
                "answer": "I also have several years of Java on a payments service.",
                "evaluation": _evaluation(0.7, "advance"),
                "root_question_id": "java",
                "assessment_method": "cross_target",
            },
        ],
    )


# --- "reached" must mean one thing ----------------------------------------------------------


def test_docker_is_assessed_so_it_cannot_also_be_never_reached():
    """(1) The exact QA contradiction: Docker has strong evidence AND was listed as never
    reached. Its last turn was a follow-up, which is what broke the match."""
    evaluations = build_question_evaluations(PLAN, _qa_state())
    unassessed = build_unassessed_required_targets(PLAN, evaluations)

    docker = next(qe for qe in evaluations if qe.target == "Docker")
    assert docker.score == 0.85, "the follow-up's turn is the one that determined the outcome"
    assert "Docker" not in unassessed


def test_docker_summary_separates_the_turn_id_from_the_target_id():
    """The fix itself: the summary still reports the follow-up as the turn that was answered,
    while naming the coverage target it belongs to."""
    evaluations = build_question_evaluations(PLAN, _qa_state())
    docker = next(qe for qe in evaluations if qe.target == "Docker")

    assert docker.target_id == "docker"
    assert docker.question_id == "docker::fu::0"
    assert docker.question == "How did you handle image layering and build caching?"


def test_partially_assessed_target_cannot_be_never_reached():
    """(2) Distributed Systems has partial evidence - weak evidence is not the same as an
    unreached target, and must never be reported as one."""
    evaluations = build_question_evaluations(PLAN, _qa_state())
    unassessed = build_unassessed_required_targets(PLAN, evaluations)

    assert any(qe.target == "Distributed Systems" for qe in evaluations)
    assert "Distributed Systems" not in unassessed


def test_cross_target_evidence_counts_as_reached():
    """(3) A target resolved from evidence volunteered while answering a different question was
    still reached - it stopped the live interview from re-asking, so the report must agree."""
    evaluations = build_question_evaluations(PLAN, _qa_state())
    unassessed = build_unassessed_required_targets(PLAN, evaluations)

    java = next(qe for qe in evaluations if qe.target == "Java")
    assert java.assessment_method == "cross_target"
    assert java.target_id == "java"
    assert "Java" not in unassessed


def test_genuinely_untouched_targets_still_appear_as_never_reached():
    """(4) The fix must not swing the other way and hide real gaps."""
    evaluations = build_question_evaluations(PLAN, _qa_state())
    unassessed = build_unassessed_required_targets(PLAN, evaluations)

    assert set(unassessed) == {"Kubernetes", "GraphQL"}


def test_required_counts_are_consistent_between_reached_and_unreached():
    """(5) Every required target is accounted for exactly once: reached or not, never both and
    never neither."""
    evaluations = build_question_evaluations(PLAN, _qa_state())
    unassessed = build_unassessed_required_targets(PLAN, evaluations)

    required = [
        t for t in PLAN.coverage_targets if t.requirement_level == RequirementLevel.REQUIRED
    ]
    reached_ids = {qe.target_id for qe in evaluations}
    unreached_names = set(unassessed)

    assert len(required) == 5
    assert len(reached_ids) + len(unreached_names) == len(required)
    for target in required:
        in_reached = target.id in reached_ids
        in_unreached = target.target in unreached_names
        assert in_reached != in_unreached, f"{target.target} is both or neither"


# --- completion reason ----------------------------------------------------------------------


def _report(unassessed: list[str]) -> InterviewReport:
    return InterviewReport(
        interview_id="int-1",
        job_id="job-qa",
        overall_score=0.7,
        recommendation=Recommendation.HIRE,
        summary="s",
        unassessed_required_targets=unassessed,
    )


def test_completion_reason_is_sufficient_evidence_when_every_required_target_was_reached():
    """(2.1/2.3) A naturally completed interview."""
    assert _report([]).completion_reason == "sufficient_evidence"


def test_completion_reason_identifies_the_length_limit_case():
    """(2.2/2.3) Required targets left over can only mean the safety bound fired first, so the
    report must say so rather than implying the interview finished its work."""
    report = _report(["Kubernetes", "GraphQL"])
    assert report.completion_reason == "budget_exhausted"


def test_unreached_requirements_are_not_treated_as_failures():
    """(2.4/2.5) The score is scoped to assessed evidence, and the report says so explicitly -
    an unreached requirement is a gap in coverage, never a negative signal about the
    candidate."""
    report = _report(["Kubernetes", "GraphQL"])

    assert report.overall_score == 0.7, "unreached requirements do not drag the score down"
    assert "not treated as failures" in report.score_basis_note
    # They are reported, not silently dropped.
    assert report.unassessed_required_targets == ["Kubernetes", "GraphQL"]


def test_qa_scenario_report_is_internally_consistent_end_to_end():
    """(5) The whole QA scenario: no target may appear as both assessed and never reached, and
    the completion reason must match the leftovers."""
    evaluations = build_question_evaluations(PLAN, _qa_state())
    unassessed = build_unassessed_required_targets(PLAN, evaluations)
    report = InterviewReport(
        interview_id="int-qa",
        job_id="job-qa",
        overall_score=0.65,
        recommendation=Recommendation.HIRE,
        summary="s",
        question_evaluations=evaluations,
        unassessed_required_targets=unassessed,
    )

    assessed_names = {qe.target for qe in report.question_evaluations}
    assert assessed_names.isdisjoint(set(report.unassessed_required_targets))
    assert report.completion_reason == "budget_exhausted"
