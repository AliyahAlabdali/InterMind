"""Diagnose *why* occupation retrieval misses: full-rank distribution, error taxonomy, ablations.

Run from ``backend/``::

    python -m evals.diagnose_retrieval

``run_retrieval_eval`` reports how often retrieval is right. This reports what it does when it
is wrong, which is the part that tells you what to fix. Offline and deterministic, like the
rest of ``evals/``.

Four things are computed.

**Full-rank distribution.** ``match_jobspec`` is asked for all 1016 occupations, so the true
rank of the best acceptable answer is known rather than censored at 5. That separates "the
right answer was second" from "the right answer was 400th" - the first is a calibration
problem, the second a representation problem, and recall@5 alone cannot tell them apart.

**Score gap.** For each miss, the cosine score of the returned top-1 against the score of the
best acceptable occupation. A gap near zero means the ranking is a coin flip between two
similar vectors; a wide gap means the correct occupation genuinely does not look like the job
description under this representation.

**Error taxonomy.** Every miss is classified by its relationship to the correct answer, using
only SOC code structure, so the classification is mechanical rather than a judgement call:

* ``same_base`` - same 6-digit SOC, different detail suffix.
* ``credential_sibling`` - correct answer's own SOC family, but the returned title is a
  technologist / technician / assistant / aide / manager variant. The vocabulary of these
  occupations overlaps almost completely with the target; what distinguishes them is
  credential and seniority, which is carried by very few words.
* ``same_minor_group`` - same 5-digit SOC: the right corner of the taxonomy, wrong occupation.
* ``same_major_group`` - same 2-digit SOC: the right broad sector.
* ``unrelated`` - different major group entirely. These are the real failures.

**Query-field ablations.** The query text concatenates role title, seniority, summary, skills,
competencies, competency descriptions and responsibilities (``_jobspec_to_query_text``). Each
field is removed in turn and the dataset re-scored, which shows whether long free-text fields
are diluting the title signal rather than adding to it. The vectorizer is refit per variant
only on the query side; the corpus and its IDF are untouched.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

from sklearn.metrics.pairwise import cosine_similarity

from app.domain.job import JobSpec, Seniority
from app.knowledge.onet_kb import OnetKnowledgeBase
from evals.retrieval_dataset import CASES

RECALL_KS = (1, 3, 5, 10, 20, 50, 100)

_CREDENTIAL_WORDS = re.compile(
    r"\b(technologist|technologists|technician|technicians|assistant|assistants|aide|aides"
    r"|manager|managers|supervisor|supervisors|helper|helpers|clerk|clerks)\b",
    re.IGNORECASE,
)


def _soc_base(code: str) -> str:
    """``15-1252.00`` -> ``15-1252`` (the 6-digit SOC, dropping the detail suffix)."""
    return code.split(".")[0]


def _soc_minor(code: str) -> str:
    """``15-1252.00`` -> ``15-125`` (5-digit minor group)."""
    return _soc_base(code).replace("-", "")[:5]


def _soc_major(code: str) -> str:
    """``15-1252.00`` -> ``15`` (2-digit major group)."""
    return code.split("-")[0]


def _full_ranking(kb: OnetKnowledgeBase, job_spec: JobSpec) -> list[tuple[str, str, float]]:
    """Every occupation, ranked. Uses the same query vector as production."""
    sims = cosine_similarity(kb._query_vector(job_spec), kb._matrix)[0]
    order = sims.argsort()[::-1]
    return [(kb._order[i], kb.get_occupation(kb._order[i]).title, float(sims[i])) for i in order]


def _best_acceptable_rank(
    ranking: list[tuple[str, str, float]], acceptable: tuple[str, ...]
) -> tuple[int, str, float]:
    for position, (code, title, score) in enumerate(ranking, start=1):
        if code in acceptable:
            return position, title, score
    raise AssertionError("acceptable code absent from a full ranking")


def _is_credential_sibling(returned_title: str, correct_titles: list[str]) -> bool:
    """The returned occupation is the same job at a different credential or seniority level.

    Detected by title containment plus a credential word, *not* by SOC proximity, because O*NET
    files these variants under different major groups: Physical Therapist Assistants is 31-2021
    while Physical Therapists is 29-1123, and Public Relations Managers is 11-2032 while Public
    Relations Specialists is 27-3031. Classifying those by SOC distance alone would call them
    unrelated and hide the single most explainable failure mode in the taxonomy.
    """
    if not _CREDENTIAL_WORDS.search(returned_title):
        return False
    returned = _title_stems(returned_title)
    return any(len(returned & _title_stems(correct)) >= 2 for correct in correct_titles)


def _title_stems(title: str) -> set[str]:
    """Significant tokens of an occupation title, truncated to a crude common stem.

    Truncating to six characters collapses the inflections O*NET titles differ by - Engineering
    / Engineers both become ``engine``, Therapist / Therapists both ``therap`` - without
    pulling in a stemmer for a diagnostic script. Credential words are dropped so they cannot
    themselves supply the overlap that marks a credential sibling.
    """
    words = re.findall(r"[a-z]+", _CREDENTIAL_WORDS.sub(" ", title.casefold()))
    return {w[:6] for w in words if len(w) > 3 and w not in {"and", "all", "other", "except"}}


def _classify(
    returned_code: str,
    returned_title: str,
    acceptable: tuple[str, ...],
    correct_titles: list[str],
) -> str:
    bases = {_soc_base(c) for c in acceptable}
    minors = {_soc_minor(c) for c in acceptable}
    majors = {_soc_major(c) for c in acceptable}
    if _soc_base(returned_code) in bases:
        return "same_base"
    if _is_credential_sibling(returned_title, correct_titles):
        return "credential_sibling"
    if _soc_minor(returned_code) in minors:
        return "same_minor_group"
    if _soc_major(returned_code) in majors:
        return "same_major_group"
    return "unrelated"


def _strip_field(spec: JobSpec, field: str) -> JobSpec:
    data = spec.model_copy(deep=True)
    if field == "role_title":
        data.role_title = ""
    elif field == "seniority":
        data.seniority = Seniority.UNKNOWN
    elif field == "summary":
        data.summary = None
    elif field == "skills":
        data.skills = []
    elif field == "competencies":
        data.competencies = []
    elif field == "competency_descriptions":
        for competency in data.competencies:
            competency.description = None
    elif field == "responsibilities":
        data.responsibilities = []
    else:
        raise ValueError(field)
    return data


def _recall_at(ranks: list[int], k: int) -> float:
    return sum(1 for r in ranks if r <= k) / len(ranks)


def _score_dataset(kb: OnetKnowledgeBase, transform=None) -> list[int]:
    ranks = []
    for case in CASES:
        spec = transform(case.job_spec) if transform else case.job_spec
        ranking = _full_ranking(kb, spec)
        rank, _, _ = _best_acceptable_rank(ranking, case.acceptable)
        ranks.append(rank)
    return ranks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    kb = OnetKnowledgeBase()

    rows = []
    for case in CASES:
        ranking = _full_ranking(kb, case.job_spec)
        rank, correct_title, correct_score = _best_acceptable_rank(ranking, case.acceptable)
        top_code, top_title, top_score = ranking[0]
        rows.append(
            {
                "case": case,
                "rank": rank,
                "top_code": top_code,
                "top_title": top_title,
                "top_score": top_score,
                "correct_title": correct_title,
                "correct_score": correct_score,
                "gap": top_score - correct_score,
                "error": None
                if rank == 1
                else _classify(
                    top_code,
                    top_title,
                    case.acceptable,
                    [kb.get_occupation(c).title for c in case.acceptable],
                ),
            }
        )

    ranks = [r["rank"] for r in rows]

    print("=" * 78)
    print("Why occupation retrieval misses")
    print("=" * 78)
    print(f"Corpus {len(kb)} occupations, {len(CASES)} labelled cases\n")

    print("-- Full-rank distribution of the correct occupation " + "-" * 25)
    for k in RECALL_KS:
        bar = "#" * round(_recall_at(ranks, k) * 40)
        print(f"  recall@{k:<4} {_recall_at(ranks, k) * 100:5.1f}%  {bar}")
    print(f"  median rank          {statistics.median(ranks):.1f}")
    print(f"  mean rank            {statistics.fmean(ranks):.1f}")
    print(f"  worst rank           {max(ranks)}")
    print()
    print("  The correct answer is almost always near the top, so this is a ranking")
    print("  calibration problem, not a failure to represent the occupation at all.")
    print()

    misses = [r for r in rows if r["rank"] > 1]
    print("-- Error taxonomy, the " + f"{len(misses)} misses " + "-" * 40)
    taxonomy: dict[str, list[str]] = {}
    for row in misses:
        taxonomy.setdefault(row["error"], []).append(row["case"].case_id)
    for kind in (
        "same_base",
        "credential_sibling",
        "same_minor_group",
        "same_major_group",
        "unrelated",
    ):
        hits = taxonomy.get(kind, [])
        print(f"  {kind:<20} {len(hits):>2}  {', '.join(hits) if hits else '-'}")
    print()

    print("-- Score gap on misses (top-1 score minus correct score) " + "-" * 19)
    gaps = [r["gap"] for r in misses]
    print(f"  median gap           {statistics.median(gaps):.4f}")
    print(f"  mean gap             {statistics.fmean(gaps):.4f}")
    print(f"  max gap              {max(gaps):.4f}")
    tiny = [r for r in misses if r["gap"] < 0.01]
    print(f"  misses within 0.01   {len(tiny)} of {len(misses)}")
    print()
    print("  Absolute cosine scores for the whole dataset:")
    all_top = [r["top_score"] for r in rows]
    print(f"    top-1 score range  {min(all_top):.3f} - {max(all_top):.3f}")
    print(f"    top-1 score median {statistics.median(all_top):.3f}")
    print()

    print("-- Query-field ablations (recall@1 / recall@5 / median rank) " + "-" * 16)
    baseline = ranks
    print(
        f"  {'full query (shipped)':<28} {_recall_at(baseline, 1) * 100:5.1f}%  "
        f"{_recall_at(baseline, 5) * 100:5.1f}%  {statistics.median(baseline):6.1f}"
    )
    ablation_results = {}
    for field in (
        "role_title",
        "seniority",
        "summary",
        "skills",
        "competencies",
        "competency_descriptions",
        "responsibilities",
    ):
        variant = _score_dataset(kb, lambda s, f=field: _strip_field(s, f))
        ablation_results[field] = variant
        delta = (_recall_at(variant, 1) - _recall_at(baseline, 1)) * 100
        flag = "  <-- removing this HELPS" if delta > 0 else ""
        print(
            f"  {'without ' + field:<28} {_recall_at(variant, 1) * 100:5.1f}%  "
            f"{_recall_at(variant, 5) * 100:5.1f}%  "
            f"{statistics.median(variant):6.1f}   {delta:+5.1f} pp{flag}"
        )
    print()

    print("-- Per-case detail " + "-" * 58)
    for row in sorted(rows, key=lambda r: -r["rank"]):
        tag = "ok" if row["rank"] == 1 else row["error"]
        print(
            f"  rank {row['rank']:>4}  {row['case'].case_id:<26} {tag:<19} "
            f"got: {row['top_title'][:34]}"
        )
    print()

    payload = {
        "corpus": len(kb),
        "recall": {f"@{k}": _recall_at(ranks, k) for k in RECALL_KS},
        "median_rank": statistics.median(ranks),
        "mean_rank": statistics.fmean(ranks),
        "worst_rank": max(ranks),
        "taxonomy": {k: v for k, v in taxonomy.items()},
        "score_gap": {
            "median": statistics.median(gaps),
            "mean": statistics.fmean(gaps),
            "max": max(gaps),
            "misses_within_0.01": len(tiny),
            "misses": len(misses),
        },
        "ablations": {
            field: {
                "recall@1": _recall_at(variant, 1),
                "recall@5": _recall_at(variant, 5),
                "median_rank": statistics.median(variant),
            }
            for field, variant in ablation_results.items()
        },
        "per_case": [
            {
                "case_id": r["case"].case_id,
                "rank": r["rank"],
                "error": r["error"],
                "top_title": r["top_title"],
                "top_score": r["top_score"],
                "correct_title": r["correct_title"],
                "correct_score": r["correct_score"],
                "gap": r["gap"],
            }
            for r in rows
        ],
    }
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
