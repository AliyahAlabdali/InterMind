"""Domain model for LLM-based evaluation of one candidate answer, and the deterministic
follow-up policy built on top of it.

Produced by :class:`app.services.answer_evaluation.AnswerEvaluationService` and consumed by
:mod:`app.agents.interview_graph` to decide whether to advance to the next question or ask a
follow-up. Fields are deliberately concise and evidence-based - no chain-of-thought or hidden
reasoning is ever requested from the LLM or stored here.

Routing authority: the LLM's own ``decision`` field is its best single-shot guess, but a real
end-to-end test showed it can under-call a follow-up even while correctly recording a specific
gap in ``weaknesses``/``follow_up_question`` - a one-shot classification is less reliable than
deterministically re-deriving the call from the evaluation's own structured evidence signal.
:func:`resolve_follow_up_decision` is that re-derivation, and is what
:mod:`app.agents.interview_graph` actually routes on - see its docstring.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class EvaluationDecision(StrEnum):
    ADVANCE = "advance"
    FOLLOW_UP = "follow_up"


class EvidenceStrength(StrEnum):
    """Qualitative read of how much a score is actually worth trusting.

    Deliberately distinct from a raw percentage (see :func:`evidence_strength_for_score`): a
    low score from a genuinely thin/non-substantive answer (a blank turn, or something like
    "I don't know") should read to a recruiter as "we don't yet know" rather than "the
    candidate lacks this" - those are different claims, and only the former is defensible from
    one interview answer.
    """

    NOT_ASSESSED = "not_assessed"
    INSUFFICIENT = "insufficient"
    LIMITED = "limited"
    MODERATE = "moderate"
    STRONG = "strong"


#: Score bands for the qualitative evidence-strength label, evaluated top-down. Distinguishes
#: two different claims that must not be conflated (see the class docstring): ``NOT_ASSESSED``
#: (score is ``None`` - the question was never actually evaluated, e.g. a blank turn) means "we
#: have no data", while ``INSUFFICIENT`` (a real, low score - e.g. an explicit "I don't know" or
#: an off-topic answer) means "the candidate answered, but gave no evidence of this". Neither is
#: "the candidate lacks this skill" - that claim is never made.
_EVIDENCE_STRENGTH_THRESHOLDS: list[tuple[float, EvidenceStrength]] = [
    (0.8, EvidenceStrength.STRONG),
    (0.6, EvidenceStrength.MODERATE),
    (0.35, EvidenceStrength.LIMITED),
]


def evidence_strength_for_score(score: float | None) -> EvidenceStrength:
    """Map a 0-1 score (or ``None``) to a qualitative evidence label."""
    if score is None:
        return EvidenceStrength.NOT_ASSESSED
    for threshold, strength in _EVIDENCE_STRENGTH_THRESHOLDS:
        if score >= threshold:
            return strength
    return EvidenceStrength.INSUFFICIENT


class AnswerEvaluation(BaseModel):
    """Structured, evidence-based evaluation of one candidate answer to one question."""

    score: float = Field(
        ge=0.0, le=1.0, description="0 (no relevant evidence) to 1 (strong, specific evidence)."
    )
    decision: EvaluationDecision
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(
        default_factory=list,
        description="Short quotes or close paraphrases from the answer supporting the score.",
    )
    follow_up_needed: bool
    follow_up_question: str | None = Field(
        default=None,
        description="Set only when follow_up_needed is true.",
    )

    @model_validator(mode="after")
    def _reconcile_follow_up_needed(self) -> AnswerEvaluation:
        """``decision`` is authoritative for ``follow_up_needed`` (kept in sync so the two
        never contradict). ``follow_up_question`` is deliberately left as the model wrote it,
        even when ``decision`` is ``advance`` - the system's own follow-up policy (see
        :func:`resolve_follow_up_decision`) may still use it as signal independent of the
        model's own one-shot ``decision`` guess. A previous version of this validator forced
        ``follow_up_question`` to ``None`` here whenever ``decision != follow_up``, which
        silently destroyed exactly that signal whenever the model's ``decision`` field
        under-called a follow-up it had otherwise correctly identified - see the module
        docstring.
        """
        follow_up = self.decision == EvaluationDecision.FOLLOW_UP
        if self.follow_up_needed != follow_up:
            self.follow_up_needed = follow_up
        return self


#: How many follow-ups a single planned question may receive before the interview moves on
#: regardless of remaining evidence gaps - keeps the loop bounded (never recursive) rather than
#: endlessly re-probing the same target. A single, named constant so
#: ``app.agents.interview_graph`` has exactly one place that defines "the cap", not a
#: re-derived magic number.
DEFAULT_MAX_FOLLOW_UPS = 1


def resolve_follow_up_decision(
    evaluation: AnswerEvaluation,
    *,
    follow_ups_used: int,
    max_follow_ups: int = DEFAULT_MAX_FOLLOW_UPS,
) -> AnswerEvaluation:
    """The system's authoritative advance-vs-follow-up call for one evaluated answer.

    Deliberately does not just return ``evaluation.decision`` - see the module docstring for
    why that alone is not reliable enough. Instead this re-derives the call from the
    evaluation's own structured evidence signal, generically (no target/category/domain-
    specific logic of any kind):

    - Already at the follow-up cap for this question -> always ``advance``, regardless of
      evidence (bounds the loop; "already followed up on this target" and "max follow-ups
      reached" are the same cap in this architecture, since each planned question maps to
      exactly one target).
    - ``strong``/``moderate`` evidence (score-derived, see :func:`evidence_strength_for_score`)
      with a concrete, answer-grounded follow-up question available -> ``follow_up``
      (a specific, worthwhile detail was left unexplored). Without one -> ``advance``.
    - ``limited``/``insufficient`` evidence with a concrete follow-up question available ->
      ``follow_up`` (asks for the missing detail/clarification). Without one -> ``advance``:
      this is what preserves the anti-gaming rule (an explicit "I don't know"/off-topic answer
      has nothing worth probing, and the prompt instructs the model to leave
      ``follow_up_question`` empty in exactly that case - see ``answer_evaluation_v1.md``) -
      the candidate is never asked to "give an example" of something they just said they lack.
    - ``not_assessed`` (score is ``None`` - should not normally reach here; a blank answer is
      handled before the LLM is even called) -> ``advance``.

    A missing/blank ``follow_up_question`` is only ever treated as "nothing concrete to ask" -
    never as license to fabricate a generic one (rule: a follow-up must be answer-aware or not
    asked at all).

    Returns a new :class:`AnswerEvaluation` with ``decision``/``follow_up_needed``/
    ``follow_up_question`` set to reflect this final call (``score``/``strengths``/
    ``weaknesses``/``evidence`` - the LLM's actual observations - are never altered). Always
    returns a freshly normalised copy, even when the final call happens to match the model's
    own ``decision``, so a stray ``follow_up_question`` the model left set alongside an
    ``advance`` decision (now possible - see ``_reconcile_follow_up_needed``) never survives
    into the result unless the final call is actually ``follow_up``.
    """
    has_question = bool(evaluation.follow_up_question and evaluation.follow_up_question.strip())

    if follow_ups_used >= max_follow_ups:
        wants_follow_up = False
    else:
        strength = evidence_strength_for_score(evaluation.score)
        if strength in (EvidenceStrength.STRONG, EvidenceStrength.MODERATE):
            # A strong/moderate score with a real gap still worth a closer look; require both
            # a concrete question *and* a recorded weakness for the (usually thorough) strong
            # band specifically, so a merely-optional follow-up doesn't interrupt an already
            # strong, complete-looking answer.
            wants_follow_up = has_question and (
                strength is EvidenceStrength.MODERATE or bool(evaluation.weaknesses)
            )
        elif strength in (EvidenceStrength.LIMITED, EvidenceStrength.INSUFFICIENT):
            wants_follow_up = has_question
        else:  # NOT_ASSESSED
            wants_follow_up = False

    decision = EvaluationDecision.FOLLOW_UP if wants_follow_up else EvaluationDecision.ADVANCE
    return evaluation.model_copy(
        update={
            "decision": decision,
            "follow_up_needed": decision == EvaluationDecision.FOLLOW_UP,
            "follow_up_question": (
                evaluation.follow_up_question if decision == EvaluationDecision.FOLLOW_UP else None
            ),
        }
    )
