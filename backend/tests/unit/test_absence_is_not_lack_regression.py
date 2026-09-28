"""Regression tests: silence about a target is not a denial of it.

The QA reproduction. For the job description "AI Engineer with python, computer vision and NLP
skills", a candidate answered:

    "I worked on a computer vision project using Python and PyTorch to train an object
     detection model."

The OpenAI evaluator emitted a ``cross_target_evidence`` entry for NLP typed ``explicit_lack``,
with a note that said, in its own words, *"No mention of experience with NLP."* - reporting the
ABSENCE of a statement as though it were a statement. ``explicit_lack`` is conclusive in
``CONCLUSIVE_EVIDENCE_TYPES``, so NLP was marked assessed without ever being asked, all three
required targets read as reached after one answer, the interview ended, and the report claimed
the candidate had said they lacked NLP experience. They never mentioned it.

Measured on the real model: 4 of 6 identical calls produced that entry.

The rule these tests pin: a candidate cannot deny a target they never mentioned, so a
cross-target ``explicit_lack`` about a target absent from the answer is not conclusive. Genuine
volunteered denials ("I've never touched Java") are unaffected, and valid cross-target
demonstrations are unaffected.
"""

from __future__ import annotations

from app.services.cross_target_evidence import resolve_cross_target_evidence

PYTHON = {"id": "python", "target": "Python", "category": "technology"}
COMPUTER_VISION = {"id": "cv", "target": "Computer Vision", "category": "technology"}
NLP = {"id": "nlp", "target": "Natural Language Processing (NLP)", "category": "technology"}
JAVA = {"id": "java", "target": "Java", "category": "technology"}

TARGETS = [PYTHON, COMPUTER_VISION, NLP, JAVA]

#: The exact answer from the QA reproduction.
CV_ANSWER = (
    "I worked on a computer vision project using Python and PyTorch to train an object "
    "detection model."
)


def _evidence(target: str, evidence_type: str, note: str = "") -> dict:
    return {"target": target, "evidence_type": evidence_type, "note": note}


def _resolve(evidence: list[dict], *, answer: str, assessed: list[str] | None = None):
    return resolve_cross_target_evidence(
        coverage_targets=TARGETS,
        current_target_id="python",
        assessed_target_ids=assessed or [],
        cross_target_evidence=evidence,
        existing_hints={},
        answer=answer,
    )


# --- Test A: absence is not lack ------------------------------------------------------------


def test_explicit_lack_for_a_target_absent_from_the_answer_is_not_conclusive():
    """The exact failing payload from the real model."""
    resolution = _resolve(
        [
            _evidence(
                "Natural Language Processing (NLP)",
                "explicit_lack",
                "No mention of experience with Natural Language Processing.",
            )
        ],
        answer=CV_ANSWER,
    )

    assert resolution.newly_assessed_ids == [], "NLP was never mentioned - it cannot be denied"
    assert resolution.history_entries == [], "no synthesized 'candidate lacks NLP' evidence"


def test_absence_does_not_synthesize_a_lack_of_experience_claim():
    """The report sentence this produced is the most damaging part of the bug: it asserted
    something about the candidate that they never said."""
    resolution = _resolve(
        [_evidence("Natural Language Processing (NLP)", "explicit_lack", "No mention of NLP.")],
        answer=CV_ANSWER,
    )

    synthesized = " ".join(
        weakness
        for entry in resolution.history_entries
        for weakness in entry["evaluation"]["weaknesses"]
    )
    assert "do not have experience" not in synthesized
    assert "Natural Language Processing" not in synthesized


# --- Test B: a genuine volunteered denial still resolves -------------------------------------


def test_genuine_volunteered_denial_still_resolves_the_target():
    """Unchanged behaviour: the candidate actually named Java and denied it, so there is
    nothing left to probe and the target is closed exactly as before."""
    answer = "I built the service in Python. I've never touched Java at all."
    resolution = _resolve(
        [_evidence("Java", "explicit_lack", "I've never touched Java at all.")], answer=answer
    )

    assert resolution.newly_assessed_ids == ["java"]
    entry = resolution.history_entries[0]
    assert entry["evaluation"]["evidence_type"] == "explicit_lack"
    assert entry["evaluation"]["decision"] == "advance"
    assert entry["evaluation"]["score"] < 0.35
    assert entry["assessment_method"] == "cross_target"


def test_denial_is_matched_on_an_abbreviation_the_candidate_actually_used():
    """The plan names the target "Natural Language Processing (NLP)"; a candidate who denies it
    will say "NLP". Either form counts as having mentioned it."""
    answer = "I did computer vision work in Python. I have never done any NLP."
    resolution = _resolve(
        [_evidence("Natural Language Processing (NLP)", "explicit_lack", "never done any NLP")],
        answer=answer,
    )

    assert resolution.newly_assessed_ids == ["nlp"]


# --- Test C: valid cross-target demonstration is untouched -----------------------------------


def test_valid_cross_target_demonstration_still_resolves():
    """Computer Vision from the QA answer: real, specific, descriptive work. This must keep
    working - the fix must not disable cross-target evidence."""
    resolution = _resolve(
        [
            _evidence(
                "Computer Vision",
                "demonstrated",
                "I worked on a computer vision project ... to train an object detection model.",
            )
        ],
        answer=CV_ANSWER,
    )

    assert resolution.newly_assessed_ids == ["cv"]
    entry = resolution.history_entries[0]
    assert entry["evaluation"]["evidence_type"] == "demonstrated"
    assert entry["evaluation"]["score"] >= 0.8
    assert entry["assessment_method"] == "cross_target"


def test_demonstrated_evidence_is_not_subject_to_the_mention_check():
    """Deliberately narrow: only `explicit_lack` is gated. A demonstration is self-evidencing -
    it describes work - so it is resolved on the evaluator's judgement as before, with no new
    constraint that could suppress valid evidence."""
    answer = "I built the whole ingestion pipeline and the model training loop myself."
    resolution = _resolve(
        [_evidence("Computer Vision", "demonstrated", "built the model training loop")],
        answer=answer,
    )

    assert resolution.newly_assessed_ids == ["cv"]


# --- Test D: non-conclusive types keep their existing semantics -------------------------------


def test_vague_mention_remains_a_hint_and_is_never_upgraded():
    resolution = _resolve(
        [_evidence("Java", "claimed_unverified", "I've also touched Java")],
        answer="Mostly Python, though I've also touched Java.",
    )

    assert resolution.newly_assessed_ids == []
    assert resolution.updated_hints["java"] == {
        "evidence_type": "claimed_unverified",
        "note": "I've also touched Java",
    }


def test_absent_target_with_a_non_conclusive_type_is_unchanged():
    """`insufficient` was already only a hint; the fix must not change that path."""
    resolution = _resolve(
        [_evidence("Natural Language Processing (NLP)", "insufficient", "nothing about NLP")],
        answer=CV_ANSWER,
    )

    assert resolution.newly_assessed_ids == []
    assert resolution.history_entries == []


# --- Test E: the full QA payload, end to end through the resolver -----------------------------


def test_qa_reproduction_payload_resolves_only_computer_vision():
    """Both entries the real model produced in one call, resolved together."""
    resolution = _resolve(
        [
            _evidence("Computer Vision", "demonstrated", "a computer vision project"),
            _evidence(
                "Natural Language Processing (NLP)",
                "explicit_lack",
                "No mention of experience with Natural Language Processing.",
            ),
        ],
        answer=CV_ANSWER,
    )

    assert resolution.newly_assessed_ids == ["cv"]
    assert [e["root_question_id"] for e in resolution.history_entries] == ["cv"]
