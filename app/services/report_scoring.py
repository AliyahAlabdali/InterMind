"""Deterministic scoring for interview reports - no LLM involved.

Kept strictly separate from narrative generation (:mod:`app.services.report_narrative`):
every number and the final recommendation here is a pure function of the interview's
recorded plan and history, so the same completed interview always yields the same score - an
LLM is never given the chance to influence it (see :mod:`app.services.report_generation`).
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable

from app.domain.evaluation import AnswerEvidenceType, EvaluationDecision
from app.domain.interview import InterviewState
from app.domain.interview_plan import InterviewPlan, QuestionCategory, RequirementLevel
from app.domain.report import (
    CompetencyAssessment,
    EvidenceStrength,
    QuestionEvaluationSummary,
    Recommendation,
    evidence_strength_for_score,
)

__all__ = [
    "CATEGORY_WEIGHTS",
    "build_areas_to_explore",
    "build_competency_assessments",
    "build_question_evaluations",
    "build_strengths",
    "build_unassessed_required_targets",
    "compute_overall_score",
    "derive_recommendation",
    "evidence_strength_for_score",
    "flatten_unique",
]

#: Category weights for the overall score. Must sum to 1.0. Rationale: competency and
#: technology questions are weighted equally and heaviest, since they probe the candidate's
#: core behavioural/technical fit; task (situational) questions carry less weight, both
#: because the planner asks fewer of them (see ``InterviewPlannerService.task_questions``)
#: and because they assess approach rather than demonstrated experience. A category absent
#: from the interview (or with no scored questions) is dropped and the remaining weights are
#: renormalised proportionally - see :func:`compute_overall_score`.
CATEGORY_WEIGHTS: dict[QuestionCategory, float] = {
    QuestionCategory.COMPETENCY: 0.4,
    QuestionCategory.TECHNOLOGY: 0.4,
    QuestionCategory.TASK: 0.2,
}

#: Recommendation thresholds against the 0-1 overall_score, evaluated top-down (first
#: threshold met wins). Fixed and documented here - never produced or overridden by an LLM.
_RECOMMENDATION_THRESHOLDS: list[tuple[float, Recommendation]] = [
    (0.85, Recommendation.STRONG_HIRE),
    (0.65, Recommendation.HIRE),
    (0.45, Recommendation.CONSIDER),
]
_DEFAULT_RECOMMENDATION = Recommendation.NO_HIRE

_SCORE_DECIMALS = 4


def build_question_evaluations(
    plan: InterviewPlan, state: InterviewState
) -> list[QuestionEvaluationSummary]:
    """One summary per coverage target the interview has evidence for, using its LAST turn.

    A target that received a follow-up has two turns in ``state.history``: the original and
    the follow-up, each with its *own* ``question_id``/``question`` text (see
    ``app.agents.interview_graph.evaluate_answer``) but sharing the same ``root_question_id``
    (the target they both belong to). Grouping by ``root_question_id`` - not ``question_id`` -
    is what lets the follow-up's turn still correctly supersede the original's as "the answer
    that actually determined whether the interview advanced" (see
    :class:`QuestionEvaluationSummary`), while the summary itself reports the follow-up's own
    id/text rather than silently attributing its answer to the original question. A turn
    without a recorded ``root_question_id`` (older/hand-built state) falls back to grouping by
    its own ``question_id``, which reproduces the pre-follow-up-identity-fix behaviour exactly.

    Iterates ``state.history`` (via ``root_question_id`` grouping), not
    ``state.asked_question_ids`` - a real gap found after cross-target evidence
    (``app.services.cross_target_evidence``) shipped: a target resolved purely from evidence
    volunteered while answering a *different* question gets its own history entry and is added
    to ``assessed_target_ids``, but its id was never appended to ``asked_question_ids`` (that
    list is reserved for targets an actual main question was generated for - see
    ``app.agents.interview_graph``). Iterating ``asked_question_ids`` therefore silently
    dropped every cross-target-resolved target from the report entirely - real evidence that
    correctly stopped the live interview from re-asking about it, then vanished from scoring
    and the recruiter's report. Grouping by ``root_question_id`` (which every turn carries,
    including a cross-target resolution's synthesized one) fixes this with no special-casing:
    every target with real evidence appears, whether it came from a direct question or not.
    Order follows first appearance in ``state.history`` - the order evidence actually arrived
    in, not the plan's own ``coverage_targets`` order (priority-ranked, not chronological - see
    ``app.services.target_selection``).
    """
    targets_by_id = {t.id: t for t in plan.coverage_targets}

    last_turn_by_root: OrderedDict[str, dict] = OrderedDict()
    for turn in state.history:
        root_id = turn.get("root_question_id") or turn["question_id"]
        last_turn_by_root[root_id] = turn

    summaries: list[QuestionEvaluationSummary] = []
    for question_id, turn in last_turn_by_root.items():
        question = targets_by_id.get(question_id)
        if question is None:
            continue  # a follow-up's own id, not a coverage target - see the docstring

        evaluation = turn.get("evaluation")
        score = evaluation["score"] if evaluation else None
        # `.get(...)` rather than `[...]` for `evidence_type`: it's a newer field, so a
        # hand-built/legacy history dict (older checkpoints, some test fixtures) may not carry
        # it - treated as "unknown", never guessed, exactly like a blank turn's `None` score.
        evidence_type = evaluation.get("evidence_type") if evaluation else None
        summaries.append(
            QuestionEvaluationSummary(
                # The grouping key: the coverage target this turn belongs to, whether the turn
                # itself was the main question, a follow-up, or a cross-target resolution.
                target_id=question_id,
                # The turn actually shown to the candidate - a follow-up reports its own id and
                # text here, so its answer is never attributed to the original question.
                question_id=turn["question_id"],
                question=turn.get("question") or question.target,
                category=question.category,
                target=question.target,
                candidate_answer=turn.get("answer") or "",
                score=score,
                decision=EvaluationDecision(evaluation["decision"]) if evaluation else None,
                evidence_type=AnswerEvidenceType(evidence_type) if evidence_type else None,
                evidence=evaluation["evidence"] if evaluation else [],
                strengths=evaluation["strengths"] if evaluation else [],
                weaknesses=evaluation["weaknesses"] if evaluation else [],
                # `.get(...)` with a "direct" default: a normal main-question turn never sets
                # this key at all (see app.agents.interview_graph.evaluate_answer) - only a
                # cross-target-resolution's synthesized turn does (see
                # app.services.cross_target_evidence.resolve_cross_target_evidence), so its
                # absence unambiguously means "an actual question was asked about this".
                assessment_method=turn.get("assessment_method", "direct"),
            )
        )
    return summaries


def build_unassessed_required_targets(
    plan: InterviewPlan, question_evaluations: list[QuestionEvaluationSummary]
) -> list[str]:
    """Required coverage targets from ``plan`` that the (adaptive) interview never reached.

    Distinct from a target that *was* asked about but produced weak evidence (that shows up in
    ``question_evaluations``/``build_competency_assessments`` with a low evidence strength
    instead, never here) - an entry returned here means literally no question was ever
    generated for it and no evidence was ever volunteered about it (directly or via cross-
    target evidence - see ``app.services.cross_target_evidence``), because the adaptive
    interview ended (budget exhausted, or the candidate simply stopped) before reaching it.
    Matched on ``QuestionEvaluationSummary.target_id`` - the coverage target each summary is
    *about* - never by name (two different-category targets can share one) and never by
    ``question_id`` (that identifies the turn, and is the follow-up's own id whenever a target's
    last turn was a follow-up; see :func:`build_question_evaluations`).
    """
    # `target_id`, never `question_id`: a target whose last turn was a follow-up carries the
    # follow-up's own id in `question_id`, so matching on that reported a target that had been
    # asked, answered and scored as "never reached" (the Docker/Distributed Systems
    # inconsistency). `target_id` is the coverage target the summary is *about*, which is the
    # only thing "reached" can consistently mean. Falls back to `question_id` for hand-built or
    # legacy summaries that predate `target_id`, where the two were by definition the same.
    evaluated_ids = {(qe.target_id or qe.question_id) for qe in question_evaluations}
    return [
        target.target
        for target in plan.coverage_targets
        if target.requirement_level == RequirementLevel.REQUIRED and target.id not in evaluated_ids
    ]


def build_competency_assessments(
    question_evaluations: list[QuestionEvaluationSummary],
) -> list[CompetencyAssessment]:
    """Group question evaluations by target, in order of first appearance.

    A target is normally backed by exactly one question (``InterviewPlannerService`` asks one
    question per selected competency/technology/task), but this aggregates correctly even if
    more than one question ever targets the same name. ``score`` is the mean of that target's
    scored questions, or ``None`` if none were scored - never guessed.
    """
    by_target: OrderedDict[str, list[QuestionEvaluationSummary]] = OrderedDict()
    for qe in question_evaluations:
        by_target.setdefault(qe.target, []).append(qe)

    assessments: list[CompetencyAssessment] = []
    for target, evaluations in by_target.items():
        scored = [e.score for e in evaluations if e.score is not None]
        score = round(sum(scored) / len(scored), _SCORE_DECIMALS) if scored else None

        # evidence_type/assessment_method mirror the module's own "last turn determines the
        # outcome" convention (see build_question_evaluations) - the most recent evaluated
        # question for this target is what actually determines what's true about it now, not
        # an earlier attempt.
        evidence_type = next(
            (e.evidence_type for e in reversed(evaluations) if e.evidence_type is not None), None
        )
        assessments.append(
            CompetencyAssessment(
                name=target,
                category=evaluations[0].category,
                score=score,
                evidence_type=evidence_type,
                evidence=flatten_unique(e.evidence for e in evaluations),
                strengths=flatten_unique(e.strengths for e in evaluations),
                weaknesses=flatten_unique(e.weaknesses for e in evaluations),
                assessment_method=evaluations[-1].assessment_method,
            )
        )
    return assessments


def compute_overall_score(competencies: list[CompetencyAssessment]) -> float:
    """Weighted average across categories present in the interview (see ``CATEGORY_WEIGHTS``).

    Not a flat average of every question's score: each *category* (competency/technology/
    task) first gets its own average from its scored competencies, then those category
    averages are combined using the fixed weights above, renormalised over whichever
    categories actually have at least one scored competency - so the result stays a proper
    0-1 weighted mean regardless of how many questions each category happened to have.
    Returns ``0.0`` if nothing was ever scored (e.g. an interview with only blank answers).

    **Scoring semantics (adaptive-runtime review, item 8)**: this is deliberately a score of
    *the evidence the interview actually gathered*, never of "how much of the full job
    specification was verified". A required target the adaptive interview never reached (see
    ``build_unassessed_required_targets``) contributes nothing here, in either direction - it
    is not scored as a failure, and it does not get averaged in as a zero. Two interviews that
    both scored 0.9 on every question they actually asked score identically here even if one
    covered every required target and the other left several unreached; only
    ``InterviewReport.unassessed_required_targets`` (and the report's wording - see
    ``app.services.report_generation``/``app.services.report_narrative``) tells that difference
    apart. This is an intentional design choice, not an oversight: penalizing a target for
    never being reached would conflate "the adaptive interview ended before asking" with "the
    candidate failed", which is exactly the report-wording problem this review exists to fix.
    """
    by_category: dict[QuestionCategory, list[float]] = {}
    for c in competencies:
        if c.score is not None:
            by_category.setdefault(c.category, []).append(c.score)

    if not by_category:
        return 0.0

    category_scores = {
        category: sum(scores) / len(scores) for category, scores in by_category.items()
    }

    total_weight = sum(CATEGORY_WEIGHTS.get(category, 0.0) for category in category_scores)
    if total_weight <= 0:
        # None of the present categories carry a configured weight - shouldn't happen with
        # the three known categories, but fall back to an unweighted mean rather than /0.
        return round(sum(category_scores.values()) / len(category_scores), _SCORE_DECIMALS)

    weighted_sum = sum(
        score * CATEGORY_WEIGHTS.get(category, 0.0) for category, score in category_scores.items()
    )
    return round(weighted_sum / total_weight, _SCORE_DECIMALS)


def derive_recommendation(overall_score: float) -> Recommendation:
    """Fixed, documented thresholds - evaluated top-down, first match wins.

    Operates purely on ``overall_score``, which is itself scoped to assessed evidence only
    (see ``compute_overall_score``) - so this recommendation is never a claim that every
    required qualification was verified, only that the qualifications actually assessed
    produced this much evidence. A "strong_hire" alongside a non-empty
    ``InterviewReport.unassessed_required_targets`` is not a contradiction: it means the
    interview evidence gathered so far is strong, not that nothing remains to check (see
    ``app.services.report_narrative``'s explicit ban on phrasing like "meets all required
    qualifications").
    """
    for threshold, recommendation in _RECOMMENDATION_THRESHOLDS:
        if overall_score >= threshold:
            return recommendation
    return _DEFAULT_RECOMMENDATION


_EXPLORE_RANK: dict[EvidenceStrength, int] = {
    EvidenceStrength.NOT_ASSESSED: 0,
    EvidenceStrength.INSUFFICIENT: 1,
    EvidenceStrength.LIMITED: 2,
    EvidenceStrength.MODERATE: 3,
    EvidenceStrength.STRONG: 4,
}


def build_strengths(competencies: list[CompetencyAssessment], limit: int = 5) -> list[str]:
    """A small, deduplicated "{competency}: {reason}" list, best-evidenced first.

    Only ever uses a strength string a competency already recorded - never invents one for a
    competency that has none, so a candidate with weak overall evidence correctly gets a short
    (or empty) list rather than a padded one.
    """
    ranked = sorted(competencies, key=lambda c: -(c.score or 0.0))
    notes: list[str] = []
    for c in ranked:
        if not c.strengths:
            continue
        notes.append(f"{c.name}: {c.strengths[0]}")
        if len(notes) >= limit:
            break
    return notes


def build_areas_to_explore(competencies: list[CompetencyAssessment], limit: int = 4) -> list[str]:
    """A small, prioritised "{competency}: {reason}" list, weakest evidence first.

    Deliberately not "every recorded weakness for every competency" (that reads as
    repetitive/padded to a recruiter) - one note per competency, ranked by how little evidence
    was gathered. A competency with insufficient evidence but no specific weakness text on
    record (e.g. a blank turn, or a follow-up cap forced advancement past it) still gets a
    plain, honest "no conclusive evidence" note rather than being silently dropped or having a
    critique invented for it.
    """
    ranked = sorted(competencies, key=lambda c: _EXPLORE_RANK[c.evidence_strength])
    notes: list[str] = []
    for c in ranked:
        if len(notes) >= limit:
            break
        if c.weaknesses:
            notes.append(f"{c.name}: {c.weaknesses[0]}")
        elif c.evidence_strength in (EvidenceStrength.INSUFFICIENT, EvidenceStrength.NOT_ASSESSED):
            notes.append(f"{c.name}: {_synthesized_gap_note(c.evidence_type)}")
    return notes


#: Honest, evidence-grounded fallback note per evidence type, used only when a competency has
#: no recorded weakness text of its own (e.g. a blank turn) - see build_areas_to_explore. Keeps
#: the same distinction the rest of this evidence-type work exists for: "explicitly stated no
#: experience" and "answered but gave nothing verifiable" are different claims, never collapsed
#: into one generic sentence.
_GAP_NOTE_BY_EVIDENCE_TYPE: dict[AnswerEvidenceType, str] = {
    AnswerEvidenceType.EXPLICIT_LACK: (
        "The candidate stated they do not have this experience - not independently verified "
        "beyond their own statement."
    ),
    AnswerEvidenceType.CLAIMED_UNVERIFIED: (
        "The candidate claimed relevant experience but could not provide detail to verify it - "
        "worth exploring further."
    ),
    AnswerEvidenceType.CONTRADICTORY: (
        "The candidate's answer contained inconsistent statements about this area - worth "
        "clarifying directly."
    ),
}
_DEFAULT_GAP_NOTE = (
    "No conclusive evidence was gathered for this area during the interview - worth exploring "
    "further."
)


def _synthesized_gap_note(evidence_type: AnswerEvidenceType | None) -> str:
    if evidence_type is None:
        return _DEFAULT_GAP_NOTE
    return _GAP_NOTE_BY_EVIDENCE_TYPE.get(evidence_type, _DEFAULT_GAP_NOTE)


def flatten_unique(lists: Iterable[list[str]]) -> list[str]:
    """Concatenate ``lists``, dropping duplicates while preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for lst in lists:
        for item in lst:
            if item not in seen:
                seen.add(item)
                result.append(item)
    return result
