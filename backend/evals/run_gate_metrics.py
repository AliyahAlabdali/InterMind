"""Binary-classification metrics for the grounding gate, plus a threshold sweep.

Run from ``backend/``::

    python -m evals.run_gate_metrics

Offline and deterministic, like the rest of ``evals/``.

**Why precision / recall / F1 belong here and not in the retrieval harness.** Picking one
occupation out of 1016 is a *ranking* task with a single right answer, so "precision@1",
"recall@1" and "accuracy" all collapse onto the same quantity - the share of cases whose top
result was acceptable - and an F1 of a number with itself is that number again. Reporting them
separately there would imply three independent measurements where there is one. The standard
metrics for that shape of problem are success@k, MRR and the rank distribution, which
``run_retrieval_eval`` and ``diagnose_retrieval`` report.

The grounding gate is a different shape. ``_match_is_grounded`` makes a genuine binary decision
- use this occupation's context, or abstain - against a genuine binary truth: was the match
acceptable. That gives a real 2x2 confusion matrix, so precision, recall, F1, specificity,
balanced accuracy and MCC are all well defined and all say something different. MCC is included
because the class balance here is uneven (most matches are wrong), and accuracy and F1 both
flatter a classifier on an unbalanced set in ways MCC does not.

**The threshold sweep** asks the question that decides whether the gate is fixable by retuning.
The gate's load-bearing signal is the best TF-IDF relevance of the matched occupation's core
tasks to the JobSpec, thresholded at ``_MIN_GROUNDING_TASK_RELEVANCE``. Sweeping that threshold
across its whole range and reporting ROC-AUC and average precision shows whether *any* cut
point separates correct matches from wrong ones. An AUC near 0.5 would mean the signal carries
no separating information on this dataset and no amount of tuning will help - the gate would
need a different signal, not a different number.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sklearn.metrics import average_precision_score, roc_auc_score

from app.knowledge.onet_kb import OnetKnowledgeBase
from app.services.interview_planner import (
    _MIN_GROUNDING_TASK_RELEVANCE,
    _MIN_RELIABLE_SCORE,
)
from evals.retrieval_dataset import CASES


def _signals(kb: OnetKnowledgeBase) -> list[dict]:
    """Per case: the two gate inputs, the gate's decision, and whether the match was correct."""
    rows = []
    for case in CASES:
        matches = kb.match_jobspec(case.job_spec, top_k=5)
        top = matches[0]
        occupation = kb.get_occupation(top.onet_soc_code)
        relevances = [
            kb.relevance_to_jobspec(case.job_spec, task) for task in occupation.core_tasks
        ]
        best_task_relevance = max(relevances) if relevances else 0.0
        grounded = top.score >= _MIN_RELIABLE_SCORE and any(
            r >= _MIN_GROUNDING_TASK_RELEVANCE for r in relevances
        )
        rows.append(
            {
                "case_id": case.case_id,
                "correct": top.onet_soc_code in case.acceptable,
                "top_score": top.score,
                "best_task_relevance": best_task_relevance,
                "grounded": grounded,
                "top_title": top.title,
            }
        )
    return rows


def _confusion(rows: list[dict], predict) -> tuple[int, int, int, int]:
    """(tp, fp, fn, tn) where a positive prediction means 'use this match'."""
    tp = fp = fn = tn = 0
    for row in rows:
        predicted = predict(row)
        if predicted and row["correct"]:
            tp += 1
        elif predicted and not row["correct"]:
            fp += 1
        elif not predicted and row["correct"]:
            fn += 1
        else:
            tn += 1
    return tp, fp, fn, tn


def _metrics(tp: int, fp: int, fn: int, tn: int) -> dict:
    total = tp + fp + fn + tn
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision and recall and (precision + recall)
        else 0.0
    )
    denominator = ((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)) ** 0.5
    mcc = ((tp * tn) - (fp * fn)) / denominator if denominator else 0.0
    balanced = (
        (recall + specificity) / 2 if recall is not None and specificity is not None else None
    )
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "accuracy": (tp + tn) / total if total else None,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "balanced_accuracy": balanced,
        "mcc": mcc,
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:5.1f}%"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    kb = OnetKnowledgeBase()
    rows = _signals(kb)
    n_correct = sum(r["correct"] for r in rows)

    shipped = _metrics(*_confusion(rows, lambda r: r["grounded"]))

    print("=" * 78)
    print("Grounding gate as a binary classifier")
    print("=" * 78)
    print(f"{len(rows)} cases: {n_correct} acceptable matches, {len(rows) - n_correct} wrong")
    print("Positive prediction = 'use this occupation's O*NET context'")
    print()

    print("-- Confusion matrix, shipped thresholds " + "-" * 37)
    print(f"  score floor          {_MIN_RELIABLE_SCORE}")
    print(f"  task-relevance floor {_MIN_GROUNDING_TASK_RELEVANCE}")
    print()
    print("                      match correct   match wrong")
    print(f"    used context        {shipped['tp']:>8}      {shipped['fp']:>8}")
    print(f"    abstained           {shipped['fn']:>8}      {shipped['tn']:>8}")
    print()

    print("-- Metrics " + "-" * 66)
    print(
        f"  precision            {_pct(shipped['precision'])}   of matches it used, "
        "this share were right"
    )
    print(
        f"  recall               {_pct(shipped['recall'])}   of right matches, this share were used"
    )
    print(
        f"  specificity          {_pct(shipped['specificity'])}   of wrong matches, "
        "this share were refused"
    )
    print(f"  F1                   {shipped['f1'] * 100:5.1f}%")
    print(f"  balanced accuracy    {_pct(shipped['balanced_accuracy'])}")
    print(f"  accuracy             {_pct(shipped['accuracy'])}")
    print(f"  MCC                  {shipped['mcc']:+.3f}   (0 = no better than chance)")
    print()
    print("  Recall is high and precision is low: the gate rarely blocks a correct")
    print("  match, and rarely blocks a wrong one either. It is tuned permissively.")
    print()

    truth = [1 if r["correct"] else 0 for r in rows]
    signal = [r["best_task_relevance"] for r in rows]
    auc = roc_auc_score(truth, signal)
    ap = average_precision_score(truth, signal)
    base_rate = n_correct / len(rows)

    print("-- Is the signal separable at all? " + "-" * 42)
    print(f"  ROC-AUC              {auc:.3f}   (0.5 = no separating information)")
    print(f"  average precision    {ap:.3f}   (base rate {base_rate:.3f})")
    print()

    print("-- Threshold sweep on best-task-relevance " + "-" * 35)
    print("  (score floor held at the shipped value)")
    print("   threshold   prec   recall   spec     F1     MCC   used")
    candidates = sorted({round(r["best_task_relevance"], 4) for r in rows} | {0.0})
    sweep = []
    for threshold in candidates:
        metrics = _metrics(
            *_confusion(
                rows,
                lambda r, t=threshold: (
                    r["top_score"] >= _MIN_RELIABLE_SCORE and r["best_task_relevance"] >= t
                ),
            )
        )
        sweep.append({"threshold": threshold, **metrics})
        marker = "  <-- shipped" if abs(threshold - _MIN_GROUNDING_TASK_RELEVANCE) < 1e-9 else ""
        print(
            f"   {threshold:9.4f}  {_pct(metrics['precision'])} {_pct(metrics['recall'])} "
            f"{_pct(metrics['specificity'])}  {metrics['f1'] * 100:5.1f}% "
            f"{metrics['mcc']:+.3f}  {metrics['tp'] + metrics['fp']:>4}{marker}"
        )
    best_f1 = max(sweep, key=lambda s: s["f1"])
    best_mcc = max(sweep, key=lambda s: s["mcc"])
    print()
    print(
        f"  best F1   at threshold {best_f1['threshold']:.4f}: "
        f"F1 {best_f1['f1'] * 100:.1f}%, precision {_pct(best_f1['precision']).strip()}, "
        f"recall {_pct(best_f1['recall']).strip()}"
    )
    print(
        f"  best MCC  at threshold {best_mcc['threshold']:.4f}: "
        f"MCC {best_mcc['mcc']:+.3f}, precision {_pct(best_mcc['precision']).strip()}, "
        f"recall {_pct(best_mcc['recall']).strip()}"
    )
    print()

    payload = {
        "cases": len(rows),
        "positives": n_correct,
        "shipped_thresholds": {
            "score_floor": _MIN_RELIABLE_SCORE,
            "task_relevance_floor": _MIN_GROUNDING_TASK_RELEVANCE,
        },
        "shipped": shipped,
        "separability": {"roc_auc": auc, "average_precision": ap, "base_rate": base_rate},
        "sweep": sweep,
        "best_f1": best_f1,
        "best_mcc": best_mcc,
        "per_case": rows,
    }
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
