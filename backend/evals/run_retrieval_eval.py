"""Measure O*NET occupation retrieval: accuracy, the fragment-downweighting A/B, and latency.

Run from ``backend/``::

    python -m evals.run_retrieval_eval                  # human-readable report
    python -m evals.run_retrieval_eval --json out.json  # also write machine-readable results

No API key and no network: ``match_jobspec`` is deterministic TF-IDF cosine similarity, so
every number here is reproducible from the tracked ``onet_kb.jsonl`` artifact alone.

Three things are measured.

**Accuracy** - recall@1/@3/@5 and MRR over ``evals.retrieval_dataset.CASES``. A case is a hit at
k when any of its ``acceptable`` SOC codes appears in the top k. Reported over all 30 cases and
split by unambiguous vs. ambiguous, because a single-label case is the stricter test.

**The FRAGMENT_WEIGHT A/B** - the same dataset scored at the shipped weight (0.5) and with
query-side fragment downweighting disabled (1.0). At 1.0 fragments are still collected and the
vector is still renormalised, and since the transformed query vector is already unit-norm,
scaling by 1.0 then renormalising is an identity - so 1.0 is a faithful "before the fix"
baseline rather than a different code path. This turns the Orthoptists bug documented in
``onet_kb.FRAGMENT_WEIGHT`` into a measured delta instead of an anecdote.

**Latency** - wall-clock ``match_jobspec`` time per query (p50/p95/p99 over repeated trials),
plus one-off index build time. Retrieval is in-process and CPU-bound, so these are stable on a
given machine; they are not a claim about end-to-end request latency, which is dominated by the
LLM calls on either side of this stage and is not measured here.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from app.knowledge import onet_kb as onet_kb_module
from app.knowledge.onet_kb import OnetKnowledgeBase
from evals.retrieval_dataset import CASES, RetrievalCase

#: Ranks at which recall is reported.
KS = (1, 3, 5)
#: How many times each query is re-run for the latency distribution.
LATENCY_TRIALS = 20


@dataclass
class CaseResult:
    case: RetrievalCase
    returned: list[tuple[str, str, float]]  # (soc_code, title, score)

    @property
    def rank(self) -> int | None:
        """1-based rank of the first acceptable code, or None if absent from the returned list."""
        for position, (code, _title, _score) in enumerate(self.returned, start=1):
            if code in self.case.acceptable:
                return position
        return None

    def hit_at(self, k: int) -> bool:
        rank = self.rank
        return rank is not None and rank <= k

    @property
    def reciprocal_rank(self) -> float:
        rank = self.rank
        return 1.0 / rank if rank is not None else 0.0


def _run_dataset(kb: OnetKnowledgeBase, top_k: int = max(KS)) -> list[CaseResult]:
    results = []
    for case in CASES:
        matches = kb.match_jobspec(case.job_spec, top_k=top_k)
        results.append(
            CaseResult(
                case=case,
                returned=[(m.onet_soc_code, m.title, m.score) for m in matches],
            )
        )
    return results


def _summarise(results: list[CaseResult]) -> dict:
    n = len(results)
    return {
        "cases": n,
        "recall": {f"@{k}": sum(r.hit_at(k) for r in results) / n for k in KS},
        "mrr": sum(r.reciprocal_rank for r in results) / n,
        "misses_at_1": [r.case.case_id for r in results if not r.hit_at(1)],
        "misses_at_5": [r.case.case_id for r in results if not r.hit_at(5)],
    }


def _measure_latency(kb: OnetKnowledgeBase, trials: int = LATENCY_TRIALS) -> dict:
    """Per-query wall-clock time for ``match_jobspec``, across every case and trial."""
    samples_ms: list[float] = []
    for _ in range(trials):
        for case in CASES:
            start = time.perf_counter()
            kb.match_jobspec(case.job_spec, top_k=5)
            samples_ms.append((time.perf_counter() - start) * 1000.0)
    samples_ms.sort()
    return {
        "queries_timed": len(samples_ms),
        "trials_per_case": trials,
        "mean_ms": statistics.fmean(samples_ms),
        "p50_ms": _percentile(samples_ms, 50),
        "p95_ms": _percentile(samples_ms, 95),
        "p99_ms": _percentile(samples_ms, 99),
        "min_ms": samples_ms[0],
        "max_ms": samples_ms[-1],
    }


def _percentile(sorted_samples: list[float], pct: float) -> float:
    """Nearest-rank percentile; `sorted_samples` must already be ascending and non-empty."""
    if not sorted_samples:
        raise ValueError("no samples")
    index = max(0, min(len(sorted_samples) - 1, round(pct / 100 * len(sorted_samples) + 0.5) - 1))
    return sorted_samples[index]


def _build_kb_timed(kb_path: Path | None) -> tuple[OnetKnowledgeBase, float]:
    start = time.perf_counter()
    kb = OnetKnowledgeBase(kb_path) if kb_path else OnetKnowledgeBase()
    return kb, (time.perf_counter() - start) * 1000.0


def _with_fragment_weight(weight: float, kb_path: Path | None) -> tuple[list[CaseResult], dict]:
    """Score the dataset with ``FRAGMENT_WEIGHT`` set to ``weight``.

    The constant is read from the module global at call time inside
    ``_downweight_fragments``, so patching the attribute changes behaviour without rebuilding
    the index or touching the fitted vectorizer. Restored in ``finally`` so one variant cannot
    leak into the next.
    """
    original = onet_kb_module.FRAGMENT_WEIGHT
    onet_kb_module.FRAGMENT_WEIGHT = weight
    try:
        kb, _ = _build_kb_timed(kb_path)
        results = _run_dataset(kb)
        return results, _summarise(results)
    finally:
        onet_kb_module.FRAGMENT_WEIGHT = original


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None, help="write results to this path")
    parser.add_argument("--kb", type=Path, default=None, help="override the knowledge-base path")
    parser.add_argument(
        "--trials", type=int, default=LATENCY_TRIALS, help="latency trials per case"
    )
    args = parser.parse_args(argv)

    kb, build_ms = _build_kb_timed(args.kb)
    shipped_results = _run_dataset(kb)
    shipped = _summarise(shipped_results)
    latency = _measure_latency(kb, trials=args.trials)

    unambiguous = _summarise([r for r in shipped_results if not r.case.ambiguous])
    ambiguous = _summarise([r for r in shipped_results if r.case.ambiguous])

    _, baseline = _with_fragment_weight(1.0, args.kb)

    print("=" * 78)
    print("O*NET occupation retrieval - offline evaluation")
    print("=" * 78)
    print(f"Knowledge base : {len(kb)} occupations")
    print(f"Index build    : {build_ms:.0f} ms (TF-IDF fit over the full corpus, at startup)")
    print(f"Dataset        : {shipped['cases']} labelled job descriptions")
    print(f"Python         : {platform.python_version()} on {platform.platform()}")
    print()

    print(f"-- Accuracy (shipped: FRAGMENT_WEIGHT = {onet_kb_module.FRAGMENT_WEIGHT}) " + "-" * 24)
    for k in KS:
        print(f"  recall@{k:<2}            {_fmt_pct(shipped['recall'][f'@{k}'])}")
    print(f"  MRR                  {shipped['mrr']:.3f}")
    print(
        f"  unambiguous only     {_fmt_pct(unambiguous['recall']['@1'])} @1 "
        f"({unambiguous['cases']} cases)"
    )
    print(
        f"  ambiguous only       {_fmt_pct(ambiguous['recall']['@1'])} @1 "
        f"({ambiguous['cases']} cases)"
    )
    if shipped["misses_at_1"]:
        print(f"  missed @1            {', '.join(shipped['misses_at_1'])}")
    if shipped["misses_at_5"]:
        print(f"  missed @5            {', '.join(shipped['misses_at_5'])}")
    print()

    print("-- Query-side fragment downweighting, A/B " + "-" * 35)
    print("   weight   recall@1   recall@5      MRR")
    for label, summary in (("1.0 (off)", baseline), ("0.5 (shipped)", shipped)):
        print(
            f"   {label:<14}{_fmt_pct(summary['recall']['@1']):>7}   "
            f"{_fmt_pct(summary['recall']['@5']):>8}   {summary['mrr']:>6.3f}"
        )
    delta_at_1 = shipped["recall"]["@1"] - baseline["recall"]["@1"]
    print(f"   delta recall@1  {delta_at_1 * 100:+.1f} pp")
    regressed = sorted(set(shipped["misses_at_1"]) - set(baseline["misses_at_1"]))
    fixed = sorted(set(baseline["misses_at_1"]) - set(shipped["misses_at_1"]))
    print(f"   fixed by it     {', '.join(fixed) if fixed else 'none'}")
    print(f"   regressed by it {', '.join(regressed) if regressed else 'none'}")
    print()

    print("-- Latency, match_jobspec " + "-" * 51)
    print(
        f"  queries timed        {latency['queries_timed']} "
        f"({latency['trials_per_case']} trials x {len(CASES)} cases)"
    )
    for key in ("mean_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms"):
        print(f"  {key:<20} {latency[key]:.2f} ms")
    print()

    print("-- Per-case detail " + "-" * 58)
    for result in sorted(shipped_results, key=lambda r: (r.rank or 99, r.case.case_id)):
        rank = result.rank
        mark = "ok " if rank == 1 else ("~  " if rank else "MISS")
        top_code, top_title, top_score = result.returned[0]
        rank_text = f"rank {rank}" if rank else "not in top 5"
        print(
            f"  {mark} {result.case.case_id:<26} {rank_text:<13} top: {top_title} ({top_score:.3f})"
        )
    print()

    payload = {
        "knowledge_base": {"occupations": len(kb), "index_build_ms": build_ms},
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "accuracy": {
            "all": shipped,
            "unambiguous": unambiguous,
            "ambiguous": ambiguous,
        },
        "fragment_weight_ab": {
            "shipped_weight": onet_kb_module.FRAGMENT_WEIGHT,
            "baseline_weight": 1.0,
            "shipped": baseline | shipped,
            "baseline": baseline,
            "delta_recall_at_1_pp": delta_at_1 * 100,
            "fixed_by_downweighting": fixed,
            "regressed_by_downweighting": regressed,
        },
        "latency": latency,
        "per_case": [
            {
                "case_id": r.case.case_id,
                "ambiguous": r.case.ambiguous,
                "tags": list(r.case.tags),
                "acceptable": list(r.case.acceptable),
                "rank": r.rank,
                "returned": [{"soc": c, "title": t, "score": s} for c, t, s in r.returned],
            }
            for r in shipped_results
        ],
    }
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
