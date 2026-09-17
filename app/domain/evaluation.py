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


class AnswerEvidenceType(StrEnum):
    """What *kind* of evidence (if any) an answer actually provides for its target - orthogonal
    to the 0-1 ``score``/``EvidenceStrength`` band.

    Two answers can land in the same low-score band for very different reasons that a
    recruiter reading the report must not have collapsed into one another. Real-OpenAI report
    review finding: "I don't remember, but I remember all of my project using MATLAB and C++
    language" (asked about Java) was reported as "the candidate did not demonstrate experience
    with Java" - true as far as it goes, but it reads as a much flatter, more final claim than
    what the candidate actually said (they attempted an answer and couldn't verify it, they
    never denied Java experience), and a *different* answer - "I don't have projects with
    python, all of my projects are around Java and OOP" - deserves a genuinely different label
    (an explicit statement of no Python experience). Score/``EvidenceStrength`` alone cannot
    distinguish these; ``evidence_type`` is the structured signal that does.

    - ``DEMONSTRATED``: the answer describes real, specific work that actually shows the
      target capability.
    - ``PARTIAL``: the answer describes some real work relevant to the target, but leaves a
      specific, worthwhile detail unexplored (not yet a full demonstration).
    - ``CLAIMED_UNVERIFIED``: the answer claims/asserts experience with the target (or attempts
      to answer, e.g. "I don't remember the frameworks...") but gives nothing concrete enough
      to verify the claim - never to be conflated with ``EXPLICIT_LACK``, since the candidate
      never denied having the experience, only failed to substantiate it.
    - ``EXPLICIT_LACK``: the candidate explicitly states they do not have experience with the
      target, have never used it, or only have experience with something else instead (an
      exclusivity statement implying lack of the asked-about target).
    - ``CONTRADICTORY``: the answer contains inconsistent/contradictory statements about the
      target (e.g. asserting experience, then denying it) that cannot be reconciled from the
      answer alone.
    - ``INSUFFICIENT``: the answer is off-topic, confused about what the target even is, or too
      vague/non-substantive to assess either way - and does not fit any of the more specific
      categories above.
    """

    DEMONSTRATED = "demonstrated"
    PARTIAL = "partial"
    CLAIMED_UNVERIFIED = "claimed_unverified"
    EXPLICIT_LACK = "explicit_lack"
    CONTRADICTORY = "contradictory"
    INSUFFICIENT = "insufficient"


_EVIDENCE_TYPE_LABELS: dict[AnswerEvidenceType, str] = {
    AnswerEvidenceType.EXPLICIT_LACK: "No evidence",
    AnswerEvidenceType.CONTRADICTORY: "Contradictory evidence",
    AnswerEvidenceType.CLAIMED_UNVERIFIED: "Unverified claim",
    AnswerEvidenceType.INSUFFICIENT: "Insufficient evidence",
    AnswerEvidenceType.PARTIAL: "Partial evidence",
}


def evidence_label(evidence_type: AnswerEvidenceType | None, score: float | None) -> str:
    """Human-readable evidence label for report/UI display.

    Deliberately driven primarily by ``evidence_type`` rather than the raw score: the score
    band alone (see ``evidence_strength_for_score``) cannot tell "explicitly stated no
    experience" apart from "claimed experience but couldn't verify it" apart from "gave a vague,
    non-substantive answer" - they can all land in the same low-score band, but a recruiter
    reading "No evidence" vs "Insufficient evidence" vs "Unverified claim" is being told three
    different, accurate things about what actually happened in the interview (see
    ``AnswerEvidenceType``'s docstring for the real report-review finding this fixes). Only
    ``DEMONSTRATED`` still needs the score to decide between "strong" and "moderate" phrasing,
    since that type spans both bands.
    """
    if evidence_type is None or score is None:
        return "Not assessed"
    if evidence_type is AnswerEvidenceType.DEMONSTRATED:
        return "Strong evidence" if score >= 0.8 else "Moderate evidence"
    return _EVIDENCE_TYPE_LABELS.get(evidence_type, "Insufficient evidence")


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


class CrossTargetEvidence(BaseModel):
    """Evidence about a *different* coverage target than the one actually asked about,
    discovered incidentally in an answer - e.g. a candidate answering a Python question who
    also mentions extensive Java experience along the way.

    Deliberately a narrower concept than the primary per-question evaluation: ``evidence_type``
    reuses :class:`AnswerEvidenceType`'s vocabulary, but only ``DEMONSTRATED``/``EXPLICIT_LACK``
    are ever conclusive enough on their own to resolve the other target without ever asking
    about it directly (see :mod:`app.services.cross_target_evidence`) - a real demonstration or
    an explicit denial both leave nothing further to probe, exactly like the primary-target
    policy in :func:`resolve_follow_up_decision`. Every other value (``CLAIMED_UNVERIFIED``,
    ``PARTIAL``, ``CONTRADICTORY``, ``INSUFFICIENT``) is a *hint* only - a casual "I've also
    touched Java" must never silently close out the Java question on its own.
    """

    target: str = Field(description="The other coverage target's name, exactly as given.")
    evidence_type: AnswerEvidenceType
    note: str = Field(
        default="",
        description="A short quote or close paraphrase from the answer supporting this signal.",
    )


class AnswerEvaluation(BaseModel):
    """Structured, evidence-based evaluation of one candidate answer to one question."""

    score: float = Field(
        ge=0.0, le=1.0, description="0 (no relevant evidence) to 1 (strong, specific evidence)."
    )
    evidence_type: AnswerEvidenceType = Field(
        description=(
            "What kind of evidence, if any, the answer actually provides for the target - see "
            "AnswerEvidenceType. Must reflect only what the candidate's own words support: an "
            "answer that attempts to answer but can't recall/verify a detail is "
            "`claimed_unverified`, never `explicit_lack` (reserved for the candidate explicitly "
            "denying the experience) and never `demonstrated`/`partial` (those require the "
            "answer to actually describe real, specific work)."
        )
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
    cross_target_evidence: list[CrossTargetEvidence] = Field(
        default_factory=list,
        description=(
            "Evidence for OTHER coverage targets (not the one asked about), found incidentally "
            "in this answer - see CrossTargetEvidence. Empty list when the answer says nothing "
            "about any other target; never fabricated to fill this in."
        ),
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
