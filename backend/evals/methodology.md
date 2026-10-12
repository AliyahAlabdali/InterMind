# Evaluation methodology

These three results use different units and separately versioned records. Frozen inputs and result hashes were verified offline. Raw candidate answers, transcripts, API logs, and internal review files are retained locally and are not part of this public summary.

## Follow-up F1 — v1.1 recovered

Ninety prewritten answer cases were matched by case ID to frozen human labels. A positive label meant a follow-up question was warranted. The prediction was **InterMind's final routing decision**, including its follow-up policy, rather than the raw model field. F1 is the harmonic mean of precision and recall: 27 true positives, 3 false positives, 4 false negatives, and 56 true negatives. The labels were completed before paid predictions, although the v1.0 protocol was finalized after labeling. The original final run stopped early; these 90 saved predictions were validated and analyzed under a separate v1.1 recovery method. Per-request model provenance from that incomplete run is unavailable. Cases include repeated question clusters, so they are not 90 independent interviewers or applicants.

## Evidence-backed claims — retrospective v1.1a

The source-locked inventory contains 245 distinct report assertions from 15 reports covering five authored jobs and strong, mixed, and weak personas. A claim counted as fully supported only when its substantive assertions followed from the full candidate answer without a material omitted qualifier. The published **90.20%** is the pooled descriptive share, 221/245; it is not classification accuracy. The original protocol's equal-report summary is 89.75%, because reports contain different numbers of claims.

One human reviewer adopted the final verdicts after AI-assisted review and disagreement re-evaluation. There is no documented independent pre-AI initial human claim review or original initial-claim lock. This retrospective deviation is recorded under v1.1a. Multiple claims from one answer or report are correlated; the 15 scripted reports are not a random applicant sample. The incomplete source run also lacks per-request model provenance. These verdicts do not establish numeric score accuracy or predictive hiring validity.

## P95 response latency — v1.1 targeted advance path

The live run timed the actual backend answer endpoint, including answer evaluation and next-question generation, through in-process ASGI transport. A predeclared fixture forced the advance path without changing production routing. Three predetermined warm-ups were excluded; the measurement then collected 20 usable requests for each of five jobs, 100 total. All 103 endpoint attempts were recorded. P95 is the 95th ordered duration by the nearest-rank rule, rounded from 3.8335991 seconds to **3.834 seconds**. The result excludes browser rendering and network transit and does not estimate latency across naturally occurring follow-up and terminal paths.
