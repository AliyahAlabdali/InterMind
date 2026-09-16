"""Deterministic scoring for interview reports - no LLM involved.

Kept strictly separate from narrative generation (:mod:`app.services.report_narrative`):
every number and the final recommendation here is a pure function of the interview's
recorded plan and history, so the same completed interview always yields the same score - an
LLM is never given the chance to influence it (see :mod:`app.services.report_generation`).
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable

from app.domain.evaluation import EvaluationDecision
from app.domain.interview import InterviewState
from app.domain.interview_plan import InterviewPlan, QuestionCategory
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
    """One summary per planned question actually asked, using its LAST answered turn.

    A question that received a follow-up has two turns in ``state.history``: the original and
    the follow-up, each with its *own* ``question_id``/``question`` text (see
    ``app.agents.interview_graph.evaluate_answer``) but sharing the same ``root_question_id``
    (the planned question they both belong to). Grouping by ``root_question_id`` - not
    ``question_id`` - is what lets the follow-up's turn still correctly supersede the
    original's as "the answer that actually determined whether the interview advanced" (see
    :class:`QuestionEvaluationSummary`), while the summary itself reports the follow-up's own
    id/text rather than silently attributing its answer to the original question. A turn
    without a recorded ``root_question_id`` (older/hand-built state) falls back to grouping by
    its own ``question_id``, which reproduces the pre-follow-up-identity-fix behaviour exactly.

    ``state.asked_question_ids`` also contains follow-up ids (not just planned question ids -
    see ``interview_graph.py``); only planned ids are iterated here; a follow-up's turn is
    already folded into its root's entry via ``root_question_id`` grouping, never a separate
    entry of its own. Order follows ``state.asked_question_ids`` - the order questions were
    actually asked in.
    """
    questions_by_id = {q.id: q for q in plan.questions}

    last_turn_by_root: OrderedDict[str, dict] = OrderedDict()
    for turn in state.history:
        root_id = turn.get("root_question_id") or turn["question_id"]
        last_turn_by_root[root_id] = turn

    summaries: list[QuestionEvaluationSummary] = []
    for question_id in state.asked_question_ids:
        question = questions_by_id.get(question_id)
        if question is None:
            continue  # a follow-up's own id, not a planned question - see the docstring

        turn = last_turn_by_root.get(question_id)
        if turn is None:
            continue

        evaluation = turn.get("evaluation")
        score = evaluation["score"] if evaluation else None
        summaries.append(
            QuestionEvaluationSummary(
                question_id=turn["question_id"],
                question=turn.get("question") or question.text,
                category=question.category,
                target=question.target,
                candidate_answer=turn.get("answer") or "",
                score=score,
                decision=EvaluationDecision(evaluation["decision"]) if evaluation else None,
                evidence=evaluation["evidence"] if evaluation else [],
                strengths=evaluation["strengths"] if evaluation else [],
                weaknesses=evaluation["weaknesses"] if evaluation else [],
            )
        )
    return summaries


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

        assessments.append(
            CompetencyAssessment(
                name=target,
                category=evaluations[0].category,
                score=score,
                evidence=flatten_unique(e.evidence for e in evaluations),
                strengths=flatten_unique(e.strengths for e in evaluations),
                weaknesses=flatten_unique(e.weaknesses for e in evaluations),
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
    """Fixed, documented thresholds - evaluated top-down, first match wins."""
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
            notes.append(
                f"{c.name}: No conclusive evidence was gathered for this area during the "
                "interview - worth exploring further."
            )
    return notes


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
