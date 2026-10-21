"""Pure aggregators. No network, file writes, or model predictions."""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from statistics import mean


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total == 0:
        raise ValueError("A proportion needs a nonempty denominator")
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def nearest_rank(values: list[float], percentile: float) -> float:
    if not values or not 0 < percentile <= 1:
        raise ValueError("Nonempty values and percentile in (0, 1] required")
    return sorted(values)[math.ceil(len(values) * percentile) - 1]


def followup_metrics(
    rows: list[tuple[str, str]], *, cluster_ids: list[str] | None = None,
    bootstrap_samples: int = 10_000, seed: int = 401
) -> dict:
    """(human label, policy prediction); ambiguous labels stay visible but leave primary F1."""
    valid = {"FOLLOW_UP_WARRANTED", "NO_FOLLOW_UP_WARRANTED", "AMBIGUOUS"}
    if not rows or any(label not in valid or prediction not in {"follow_up", "advance"}
                       for label, prediction in rows):
        raise ValueError("Invalid or empty follow-up rows")
    if cluster_ids is not None and len(cluster_ids) != len(rows):
        raise ValueError("Every follow-up row needs a cluster ID")
    clear = [(label == "FOLLOW_UP_WARRANTED", pred == "follow_up")
             for label, pred in rows if label != "AMBIGUOUS"]
    if not clear:
        raise ValueError("No unambiguous human labels")

    def score(sample: list[tuple[bool, bool]]) -> tuple[int, int, int, int, float]:
        tp = sum(truth and pred for truth, pred in sample)
        fp = sum(not truth and pred for truth, pred in sample)
        fn = sum(truth and not pred for truth, pred in sample)
        tn = len(sample) - tp - fp - fn
        f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0
        return tp, fp, fn, tn, f1

    tp, fp, fn, tn, f1 = score(clear)
    rng = random.Random(seed)
    if cluster_ids is None:
        clusters = [[item] for item in clear]
    else:
        grouped: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
        for (label, prediction), cluster_id in zip(rows, cluster_ids, strict=True):
            if label != "AMBIGUOUS":
                grouped[cluster_id].append(
                    (label == "FOLLOW_UP_WARRANTED", prediction == "follow_up")
                )
        clusters = list(grouped.values())
    replicates = sorted(score([item for cluster in rng.choices(clusters, k=len(clusters))
                               for item in cluster])[4]
                        for _ in range(bootstrap_samples))
    ambiguous = [pred == "follow_up" for label, pred in rows if label == "AMBIGUOUS"]
    forced = {}
    for value, name in ((False, "all_not_warranted"), (True, "all_warranted")):
        forced[name] = score(clear + [(value, pred) for pred in ambiguous])[4]
    return {
        "n_total": len(rows), "n_primary": len(clear), "n_bootstrap_clusters": len(clusters),
        "ambiguous": len(ambiguous),
        "ambiguous_share": len(ambiguous) / len(rows),
        "ambiguous_share_wilson_95": wilson(len(ambiguous), len(rows)),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "precision_wilson_95": wilson(tp, tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "recall_wilson_95": wilson(tp, tp + fn) if tp + fn else None,
        "f1": f1,
        "unnecessary_follow_up_rate": fp / (tn + fp) if tn + fp else None,
        "missed_follow_up_rate": fn / (tp + fn) if tp + fn else None,
        "f1_bootstrap_95": (replicates[int(.025 * bootstrap_samples)],
                            replicates[int(.975 * bootstrap_samples) - 1]),
        "ambiguous_sensitivity_f1": forced,
    }


def traceability_metrics(rows: list[dict], adjudications: dict[str, str]) -> dict:
    """Rows carry id/tier; every ambiguous item requires a blind human verdict."""
    if not rows:
        raise ValueError("No evidence strings")
    counts = Counter(row["tier"] for row in rows)
    if set(counts) - {"supported_exact", "supported_lexical", "ambiguous"}:
        raise ValueError("Unknown grounding tier")
    ambiguous_ids = {row["evidence_id"] for row in rows if row["tier"] == "ambiguous"}
    if set(adjudications) != ambiguous_ids or set(adjudications.values()) - {
        "supported", "unsupported", "cannot_tell"
    }:
        raise ValueError("Every ambiguous evidence string needs one valid verdict")
    automatic = counts["supported_exact"] + counts["supported_lexical"]
    supported = automatic + sum(value == "supported" for value in adjudications.values())
    cannot_tell = sum(value == "cannot_tell" for value in adjudications.values())
    n = len(rows)
    return {
        "n_evidence": n, "automatic_supported": automatic,
        "adjudicated_supported": supported - automatic,
        "adjudication_load": len(ambiguous_ids), "cannot_tell": cannot_tell,
        "traceability": supported / n, "traceability_wilson_95": wilson(supported, n),
        "unsupported_rate": (n - supported) / n,
        "unsupported_wilson_95": wilson(n - supported, n),
        "automatic_verification_rate": automatic / n,
    }


def cliffs_delta(x: list[float], y: list[float]) -> float:
    if not x or not y:
        raise ValueError("Both groups need scores")
    return (sum(a > b for a in x for b in y) - sum(a < b for a in x for b in y)) / (len(x) * len(y))


def discrimination_metrics(rows: list[dict]) -> dict:
    """One score for each (job, tier); do not infer the class from model output."""
    grouped: dict[str, dict[str, float]] = defaultdict(dict)
    recommendations: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        if row["tier"] in grouped[row["jd_id"]]:
            raise ValueError("Duplicate persona/job")
        grouped[row["jd_id"]][row["tier"]] = float(row["score"])
        recommendations[row["tier"]][row["recommendation"]] += 1
    if not grouped or any(set(scores) != {"strong", "mixed", "weak"}
                          for scores in grouped.values()):
        raise ValueError("Every job needs strong, mixed, and weak scores")
    by_tier = {tier: [scores[tier] for scores in grouped.values()]
               for tier in ("strong", "mixed", "weak")}
    strong, mixed, weak = (by_tier[t] for t in ("strong", "mixed", "weak"))
    overlap = sum(w >= s for s in strong for w in weak) / (len(strong) * len(weak))
    ordered = sum(scores["strong"] > scores["mixed"] > scores["weak"]
                  for scores in grouped.values())
    delta = cliffs_delta(strong, weak)
    return {
        "n_jobs": len(grouped), "n_personas": len(rows),
        "mean_score": {tier: mean(values) for tier, values in by_tier.items()},
        "cliffs_delta_strong_weak": delta,
        "cliffs_delta_strong_mixed": cliffs_delta(strong, mixed),
        "cliffs_delta_mixed_weak": cliffs_delta(mixed, weak),
        "weak_ge_strong_overlap": overlap,
        "ordered_jobs": ordered, "ordering_consistency": ordered / len(grouped),
        "recommendations": {tier: dict(counts) for tier, counts in recommendations.items()},
        "gate_passed": delta >= .5 and overlap <= .2 and ordered >= math.ceil(.8 * len(grouped)),
    }


def latency_metrics(rows: list[dict]) -> dict:
    kept = [float(row["seconds"]) for row in rows if row["path"] == "advance"
            and not row.get("warmup") and not row.get("retried")]
    if not kept:
        raise ValueError("No valid advance-path requests")
    return {
        "n_advance": len(kept), "p50_seconds": nearest_rank(kept, .5),
        "p95_seconds": nearest_rank(kept, .95),
        "p99_seconds": nearest_rank(kept, .99) if len(kept) >= 100 else None,
        "n_follow_up_excluded": sum(row["path"] == "follow_up" for row in rows),
        "n_finish_excluded": sum(row["path"] == "finish" for row in rows),
        "n_warmup_excluded": sum(bool(row.get("warmup")) for row in rows),
        "n_retry_excluded": sum(bool(row.get("retried")) for row in rows),
    }


def token_cost(
    events: list[dict], input_per_million: float, output_per_million: float,
    cached_input_per_million: float | None = None,
) -> dict:
    completed = [
        event for event in events if event.get("operation") == "generate_structured_completed"
    ]
    if any(event.get("prompt_tokens") is None or event.get("completion_tokens") is None
           for event in completed):
        raise ValueError("A completed API call is missing SDK token usage")
    prompt = sum(int(e["prompt_tokens"]) for e in completed)
    output = sum(int(e["completion_tokens"]) for e in completed)
    cached = sum(int(e.get("cached_prompt_tokens") or 0) for e in completed)
    if cached > prompt:
        raise ValueError("Cached input tokens exceed total input tokens")
    cached_rate = (
        input_per_million if cached_input_per_million is None else cached_input_per_million
    )
    return {"api_calls": len(completed), "prompt_tokens": prompt,
            "cached_prompt_tokens": cached, "completion_tokens": output,
            "estimated_usd": (prompt - cached) / 1_000_000 * input_per_million
            + cached / 1_000_000 * cached_rate
            + output / 1_000_000 * output_per_million}
