"""Attribute report evidence to the candidate's actual answer turns."""

from __future__ import annotations

from hashlib import sha256

from app.domain.interview import InterviewState
from app.domain.report import InterviewReport

from .grounding import classify


def extract_evidence(report: InterviewReport, state: InterviewState) -> list[dict]:
    """Return internal audit rows; callers must blind them before human review.

    Cross-target history entries store a synthesized *note* in their answer field. The
    candidate's real answer is the immediately preceding direct turn that caused the
    resolution, so using the note would audit the model against its own paraphrase.
    """
    rows: list[dict] = []
    for summary in report.question_evaluations:
        root = summary.target_id
        direct = [turn["answer"] for turn in state.history
                  if (turn.get("root_question_id") or turn.get("question_id")) == root
                  and turn.get("assessment_method", "direct") == "direct"
                  and turn.get("answer")]
        cross_sources: list[tuple[dict, str]] = []
        for index, turn in enumerate(state.history):
            if ((turn.get("root_question_id") or turn.get("question_id")) == root
                    and turn.get("assessment_method") == "cross_target"):
                preceding = next((item.get("answer") for item in reversed(state.history[:index])
                                  if item.get("assessment_method", "direct") == "direct"
                                  and item.get("answer")), None)
                if preceding is None:
                    raise ValueError("Cross-target evidence has no source candidate answer")
                cross_sources.append((turn, preceding))
        for evidence in summary.evidence:
            # The summary may accumulate evidence from both a cross-target resolution and
            # a later direct answer. Scope each string to the turn(s) that recorded it.
            origins = [turn for turn in state.history
                       if (turn.get("root_question_id") or turn.get("question_id")) == root
                       and evidence in (turn.get("evaluation") or {}).get("evidence", [])]
            sources: list[str] = []
            for origin in origins:
                if origin.get("assessment_method", "direct") == "direct":
                    sources.extend(direct)
                else:
                    sources.extend(answer for turn, answer in cross_sources if turn is origin)
            sources = list(dict.fromkeys(sources))
            if not sources:
                raise ValueError("Report evidence has no permitted source answer")
            digest = sha256(f"{report.interview_id}\0{root}\0{evidence}".encode()).hexdigest()[:20]
            result = classify(evidence, sources)
            rows.append({
                "evidence_id": f"ev-{digest}", "interview_id": report.interview_id,
                "target_id": root, "assessment_method": summary.assessment_method,
                "evidence_string": evidence, "source_answers": sources,
                "tier": result.tier.value, "coverage": result.coverage,
                "bigram_coverage": result.bigram_coverage, "guard": result.guard,
            })
    if len({r["evidence_id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate evidence identifiers")
    return rows


def blinded_adjudication(rows: list[dict]) -> list[dict]:
    """Only the pair and an opaque join key; no score, tier, model, persona or target."""
    from random import Random

    export = [{"evidence_id": r["evidence_id"], "evidence_string": r["evidence_string"],
               "source_answers": r["source_answers"], "verdict": ""}
              for r in rows if r["tier"] == "ambiguous"]
    Random(1129).shuffle(export)
    return export
