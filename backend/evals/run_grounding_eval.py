"""Measure the grounding gate: when retrieval is wrong, does InterMind decline to use it?

Run from ``backend/``::

    python -m evals.run_grounding_eval
    python -m evals.run_grounding_eval --json out.json

No API key and no network. ``InterviewPlannerService.plan`` is a pure function of the JobSpec
and the knowledge base - the LLM is not involved at this stage - so this whole harness is
deterministic and offline.

**Why this is the metric that matters.** ``match_jobspec`` returns a best-effort nearest
occupation out of 1016, and it is often not the one a human would pick: see
``evals.run_retrieval_eval`` for the recall numbers. On its own that would be a serious problem
for a hiring tool, because a misidentified occupation could contribute requirements the job
description never asked for. The architecture's answer is not to claim better retrieval but to
refuse to use a weak match: ``_match_is_grounded`` requires both an absolute score floor and a
core task that actually resembles the job, and only then is any O*NET context assembled
(``InterviewPlan.onet_grounding_used``). So the question worth measuring is not "how often is
retrieval right" but **"when the system chose to act on retrieval, was retrieval right"** - and
conversely, how reliably it abstains when retrieval is wrong.

That makes each case fall into one of four outcomes, counted here as a confusion matrix:

===========================  ==========================================================
``grounded_correct``         Match acceptable, context used. The intended good case.
``grounded_wrong``           Match not acceptable, context used anyway. **The only
                             outcome that can corrupt an interview**, so this is the
                             number to report and the number to drive to zero.
``abstained_wrong``          Match not acceptable, context suppressed. The safety
                             mechanism working: the interview falls back to the job
                             description alone, which is the documented behaviour.
``abstained_correct``        Match acceptable but context suppressed anyway. A missed
                             opportunity, not a correctness problem - conservative by
                             design, and cheap next to ``grounded_wrong``.
===========================  ==========================================================

Headline figures: **grounding precision** = ``grounded_correct / (grounded_correct +
grounded_wrong)``, and **abstention recall** = ``abstained_wrong / (abstained_wrong +
grounded_wrong)``. Both are reported with their raw counts, because on a 30-case set a single
case moves a percentage by 3.3 points.

**Limitation.** "Correct" here means the top match is in the case's ``acceptable`` set, which is
author-labelled - see ``evals.retrieval_dataset``. And a correct abstention is only *safe*, not
*accurate*: this measures that bad context is withheld, not that the resulting interview is
good, which would need the end-to-end evaluation this harness does not attempt.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from app.core.exceptions import NoOccupationMatch
from app.domain.interview_plan import EvidenceSource
from app.knowledge.onet_kb import OnetKnowledgeBase
from app.services.interview_planner import InterviewPlannerService
from evals.retrieval_dataset import CASES, RetrievalCase


@dataclass
class GroundingResult:
    case: RetrievalCase
    top_code: str | None
    top_title: str
    top_score: float
    grounded: bool
    context_chars: int
    technologies_from_onet: int
    tasks_from_onet: int
    error: str | None = None
    corroborated_items: int = 0

    @property
    def match_correct(self) -> bool:
        return self.top_code is not None and self.top_code in self.case.acceptable

    @property
    def outcome(self) -> str:
        if self.error:
            return "error"
        if self.grounded:
            return "grounded_correct" if self.match_correct else "grounded_wrong"
        return "abstained_correct" if self.match_correct else "abstained_wrong"

    @property
    def onet_items(self) -> int:
        """Technologies + tasks with ONET-only provenance, excluding JD corroboration."""
        return self.technologies_from_onet + self.tasks_from_onet

    @property
    def leaked_requirement(self) -> bool:
        """A wrong occupation supplied an ONET-only technology or task.

        BOTH means an existing JD requirement was corroborated, not introduced. The current
        planner only selects JD requirements, so ONET-only items would indicate a regression.
        This provenance-based check does not measure influence on generated question wording.
        """
        return not self.match_correct and self.grounded and self.onet_items > 0


async def _plan_case(planner: InterviewPlannerService, case: RetrievalCase) -> GroundingResult:
    try:
        plan = await planner.plan(job_id=f"eval-{case.case_id}", job_spec=case.job_spec)
    except NoOccupationMatch as exc:
        return GroundingResult(
            case=case,
            top_code=None,
            top_title="<no match>",
            top_score=0.0,
            grounded=False,
            context_chars=0,
            technologies_from_onet=0,
            tasks_from_onet=0,
            error=f"NoOccupationMatch: {exc}",
        )

    onet_techs = sum(1 for t in plan.technologies if _from_onet(t))
    onet_tasks = sum(1 for t in plan.tasks if _from_onet(t))
    corroborated = sum(
        1 for item in [*plan.technologies, *plan.tasks] if item.source == EvidenceSource.BOTH
    )
    return GroundingResult(
        case=case,
        top_code=plan.occupation_match.onet_soc_code,
        top_title=plan.occupation_match.title,
        top_score=plan.occupation_match.score,
        grounded=plan.onet_grounding_used,
        context_chars=len(plan.onet_context or ""),
        technologies_from_onet=onet_techs,
        tasks_from_onet=onet_tasks,
        corroborated_items=corroborated,
    )


def _from_onet(item) -> bool:
    """True for an O*NET-only requirement; BOTH corroborates an existing JD item."""
    return item.source == EvidenceSource.ONET


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _fmt_rate(numerator: int, denominator: int) -> str:
    if not denominator:
        return "n/a (0 cases)"
    return f"{numerator / denominator * 100:.1f}%  ({numerator}/{denominator})"


async def _main_async(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--kb", type=Path, default=None)
    args = parser.parse_args(argv)

    kb = OnetKnowledgeBase(args.kb) if args.kb else OnetKnowledgeBase()
    planner = InterviewPlannerService(knowledge_base=kb)

    results = [await _plan_case(planner, case) for case in CASES]
    counts = {
        key: sum(1 for r in results if r.outcome == key)
        for key in (
            "grounded_correct",
            "grounded_wrong",
            "abstained_wrong",
            "abstained_correct",
            "error",
        )
    }
    grounded_total = counts["grounded_correct"] + counts["grounded_wrong"]
    wrong_total = counts["grounded_wrong"] + counts["abstained_wrong"]
    correct_total = counts["grounded_correct"] + counts["abstained_correct"]

    print("=" * 78)
    print("Grounding gate - does InterMind decline to use a weak occupation match?")
    print("=" * 78)
    print(f"Knowledge base : {len(kb)} occupations")
    print(f"Dataset        : {len(CASES)} labelled job descriptions")
    print()

    print("-- Outcomes " + "-" * 65)
    for key, blurb in (
        ("grounded_correct", "match acceptable, O*NET context used"),
        ("grounded_wrong", "match wrong, context used  <-- the risk"),
        ("abstained_wrong", "match wrong, context suppressed (safe)"),
        ("abstained_correct", "match acceptable, context suppressed"),
    ):
        print(f"  {key:<20} {counts[key]:>3}   {blurb}")
    if counts["error"]:
        print(f"  error                {counts['error']:>3}")
    print()

    print("-- Headline " + "-" * 65)
    print(f"  grounding precision  {_fmt_rate(counts['grounded_correct'], grounded_total)}")
    print("                       of the interviews that used O*NET context, this share")
    print("                       were built on an acceptable occupation match")
    print(f"  abstention recall    {_fmt_rate(counts['abstained_wrong'], wrong_total)}")
    print("                       of the wrong matches, this share were correctly refused")
    print(f"  grounding rate       {_fmt_rate(grounded_total, len(results))}")
    print(f"  retrieval recall@1   {_fmt_rate(correct_total, len(results))}  (for contrast)")
    print()

    leaked = [r for r in results if r.leaked_requirement]
    context_only = [r for r in results if r.outcome == "grounded_wrong" and r.onet_items == 0]
    onet_tasks_from_wrong = sum(r.tasks_from_onet for r in results if not r.match_correct)
    corroborated_wrong = [r for r in results if not r.match_correct and r.corroborated_items]
    print("-- Did a wrong match actually add a requirement? " + "-" * 28)
    print(f"  requirement leakage  {_fmt_rate(len(leaked), len(results))} of all cases")
    print(f"                       {_fmt_rate(len(leaked), wrong_total)} of wrong matches")
    print(f"  context-block only   {len(context_only)} wrong matches cleared the gate but the")
    print("                       plan contained no ONET-only technology or task")
    print(f"  JD corroboration     {len(corroborated_wrong)} wrong matches annotated JD items")
    print(f"  tasks from a wrong   {onet_tasks_from_wrong}")
    print("    occupation")
    if leaked:
        print("  leaking cases:")
        for r in leaked:
            print(
                f"    {r.case.case_id:<24} {r.technologies_from_onet} tech / "
                f"{r.tasks_from_onet} tasks  <- {r.top_title}"
            )
    print()

    print("-- Per-case " + "-" * 65)
    label = {
        "grounded_correct": "GROUNDED (ok)",
        "grounded_wrong": "GROUNDED (WRONG)",
        "abstained_wrong": "abstained (safe)",
        "abstained_correct": "abstained (missed)",
        "error": "error",
    }
    for r in sorted(results, key=lambda r: (r.outcome, r.case.case_id)):
        print(
            f"  {label[r.outcome]:<19} {r.case.case_id:<26} "
            f"{r.top_title[:38]:<38} {r.top_score:.3f}"
        )
    print()

    if counts["grounded_wrong"]:
        print("-- Cases where a wrong match was still used " + "-" * 33)
        for r in results:
            if r.outcome == "grounded_wrong":
                print(
                    f"  {r.case.case_id}: used {r.top_title} ({r.top_score:.3f}); "
                    f"{r.technologies_from_onet} tech / {r.tasks_from_onet} ONET-only tasks, "
                    f"{r.corroborated_items} corroborated JD items, "
                    f"{r.context_chars} chars of context"
                )
                print(f"     acceptable was: {', '.join(r.case.acceptable)}")
        print()

    payload = {
        "requirement_metric_version": 2,
        "requirement_metric_definition": "ONET-only provenance; BOTH is JD corroboration",
        "knowledge_base": {"occupations": len(kb)},
        "cases": len(results),
        "counts": counts,
        "grounding_precision": _rate(counts["grounded_correct"], grounded_total),
        "abstention_recall": _rate(counts["abstained_wrong"], wrong_total),
        "grounding_rate": _rate(grounded_total, len(results)),
        "retrieval_recall_at_1": _rate(correct_total, len(results)),
        "requirement_leakage": {
            "cases": len(leaked),
            "rate_of_all": _rate(len(leaked), len(results)),
            "rate_of_wrong_matches": _rate(len(leaked), wrong_total),
            "context_block_only": len(context_only),
            "tasks_from_wrong_occupation": onet_tasks_from_wrong,
            "case_ids": [r.case.case_id for r in leaked],
        },
        "jd_corroboration_from_wrong_match": {
            "cases": len(corroborated_wrong),
            "items": sum(r.corroborated_items for r in corroborated_wrong),
            "case_ids": [r.case.case_id for r in corroborated_wrong],
        },
        "per_case": [
            {
                "case_id": r.case.case_id,
                "outcome": r.outcome,
                "top_code": r.top_code,
                "top_title": r.top_title,
                "top_score": r.top_score,
                "acceptable": list(r.case.acceptable),
                "grounded": r.grounded,
                "context_chars": r.context_chars,
                "onet_technologies": r.technologies_from_onet,
                "onet_tasks": r.tasks_from_onet,
                "corroborated_jd_items": r.corroborated_items,
                "error": r.error,
            }
            for r in results
        ],
    }
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {args.json}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main_async(argv))


if __name__ == "__main__":
    sys.exit(main())
