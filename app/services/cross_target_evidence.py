"""Deterministic resolution of cross-target evidence discovered incidentally in an answer.

A candidate answering a question about one coverage target sometimes volunteers real evidence
about a *different* one - e.g. answering a Python question but also mentioning extensive Java
experience along the way. Without this, that evidence is simply lost: the interview would have
to ask about Java separately later (redundant, if the candidate already gave a real answer) or
never surface it at all.

This module is a pure, LLM-free function over already-produced, structured
:class:`~app.domain.evaluation.CrossTargetEvidence` items (see
:class:`app.services.answer_evaluation.AnswerEvaluationService.evaluate`'s ``other_targets``
param) - it never calls an LLM itself and never receives raw model output, only the normalized
signal the evaluator already extracted. :mod:`app.services.target_selection` stays exactly as
LLM-free as before; this module is what turns "the LLM noticed something about another target"
into the same history/`assessed_target_ids` bookkeeping a normal main question produces, so the
selector never needs to know cross-target evidence exists at all - it only ever sees the result
(a target already in ``assessed_target_ids``, or not).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.text_normalize import normalize_name

#: Evidence types conclusive enough, on their own, to resolve a target the candidate wasn't
#: even asked about - mirroring the primary-target policy in
#: ``app.domain.evaluation.resolve_follow_up_decision``: a real demonstration or an explicit
#: denial both leave nothing further to probe, whether it came from a direct question or
#: incidentally from a different one. Every other evidence type (a bare claim, a partial
#: mention, a contradiction, an off-topic aside) is recorded as a hint only - see
#: ``resolve_cross_target_evidence``'s docstring for why a casual mention must never
#: auto-close a target.
CONCLUSIVE_EVIDENCE_TYPES = frozenset({"demonstrated", "explicit_lack"})


@dataclass
class CrossTargetResolution:
    """What one turn's cross-target evidence resolves to, ready to merge into graph state.

    ``history_entries`` are shaped exactly like a normal history turn (see
    ``app.agents.interview_graph``) - each carries its own ``root_question_id`` equal to the
    resolved target's id, so existing report-attribution logic
    (``app.services.report_scoring.build_question_evaluations``) picks them up with no special
    casing at all. ``newly_assessed_ids`` are the target ids to add to
    ``assessed_target_ids`` (so the selector never offers them again).
    ``updated_hints`` is the full replacement value for ``state["target_hints"]`` - a plain
    ``{target_id: {"evidence_type": ..., "note": ...}}`` map of non-conclusive signals still
    worth remembering if that target is later asked about directly.
    """

    history_entries: list[dict] = field(default_factory=list)
    newly_assessed_ids: list[str] = field(default_factory=list)
    updated_hints: dict[str, dict] = field(default_factory=dict)


def _synthesized_evaluation(evidence_type: str, target_name: str, note: str) -> dict:
    """A minimal, honest evaluation dict for a target resolved via cross-target evidence -
    same shape as a real turn's evaluation (see ``app.agents.interview_graph.evaluate_answer``),
    so report attribution can't tell the difference downstream (the caller separately sets
    ``assessment_method: "cross_target"`` on the history entry - see
    ``resolve_cross_target_evidence`` - so the report can still tell them apart when it wants
    to). Never claims more than the evidence type itself supports - phrasing mirrors the
    primary-target branches in ``app.llm.fake_client._fake_evaluate_answer`` for the same two
    conclusive types, but is explicitly labelled "Cross-target evidence" up front (adaptive-
    runtime review, item 5): the old "Volunteered relevant experience with X while answering a
    different question" phrasing read as an odd, unlabelled aside rather than a clearly
    classified kind of evidence.
    """
    if evidence_type == "demonstrated":
        return {
            "score": 0.8,
            "evidence_type": evidence_type,
            "decision": "advance",
            "strengths": [
                f"Cross-target evidence: the candidate provided relevant evidence for "
                f"{target_name} while answering a different question."
            ],
            "weaknesses": [],
            "evidence": [note] if note else [],
            "follow_up_needed": False,
            "follow_up_question": None,
        }
    return {
        "score": 0.05,
        "evidence_type": evidence_type,
        "decision": "advance",
        "strengths": [],
        "weaknesses": [
            f"Cross-target evidence: the candidate stated they do not have experience with "
            f"{target_name} while answering a different question."
        ],
        "evidence": [],
        "follow_up_needed": False,
        "follow_up_question": None,
    }


def resolve_cross_target_evidence(
    *,
    coverage_targets: list[dict],
    current_target_id: str,
    assessed_target_ids: list[str],
    cross_target_evidence: list[dict],
    existing_hints: dict[str, dict],
) -> CrossTargetResolution:
    """Turn one turn's ``cross_target_evidence`` (a list of ``{"target", "evidence_type",
    "note"}`` dicts - see :class:`~app.domain.evaluation.CrossTargetEvidence`) into concrete
    state updates.

    Deterministic and total: every item either matches a known, not-yet-assessed coverage
    target (by normalized name) or is silently ignored (an evaluator hallucinating a target
    name that isn't in the interview at all must never crash or fabricate a new one - the
    interview's own coverage_targets list is still the only source of truth for what exists).
    A target already in ``assessed_target_ids``, or already resolved earlier in this same
    call, is never resolved a second time - avoids duplicate history entries/evidence for the
    same target. ``current_target_id`` is excluded outright: cross-target evidence about the
    target actually being asked about *is* the primary evaluation, not a cross-target signal.
    """
    resolution = CrossTargetResolution(updated_hints=dict(existing_hints))
    assessed = set(assessed_target_ids)
    by_normalized_name = {
        normalize_name(t["target"]): t for t in coverage_targets if t["id"] != current_target_id
    }
    resolved_this_turn: set[str] = set()

    for item in cross_target_evidence:
        match = by_normalized_name.get(normalize_name(item["target"]))
        if match is None:
            continue  # doesn't correspond to any known coverage target - never invent one
        target_id = match["id"]
        if target_id in assessed or target_id in resolved_this_turn:
            continue  # already resolved - never duplicated

        evidence_type = item["evidence_type"]
        if evidence_type in CONCLUSIVE_EVIDENCE_TYPES:
            resolved_this_turn.add(target_id)
            resolution.newly_assessed_ids.append(target_id)
            resolution.updated_hints.pop(target_id, None)
            resolution.history_entries.append(
                {
                    "question_id": target_id,
                    "question": (
                        "(Not asked directly - identified from the candidate's answer to a "
                        "different question.)"
                    ),
                    "answer": item.get("note", ""),
                    "evaluation": _synthesized_evaluation(
                        evidence_type, match["target"], item.get("note", "")
                    ),
                    "root_question_id": target_id,
                    # The one authoritative marker report_scoring.build_question_evaluations
                    # reads to distinguish "asked directly" from "resolved incidentally" (see
                    # QuestionEvaluationSummary.assessment_method) - a real main-question turn
                    # never sets this key at all, so its absence there already means "direct".
                    "assessment_method": "cross_target",
                }
            )
        else:
            # A casual mention/claim/contradiction - worth remembering (e.g. to inform that
            # target's own question later), never enough alone to close it out.
            resolution.updated_hints[target_id] = {
                "evidence_type": evidence_type,
                "note": item.get("note", ""),
            }

    return resolution
