# Recovered follow-up and discrimination analysis method v1.1

**Scope and timing.** This method applies only to the 90 follow-up rows and 15
persona reports in the incomplete v1.0 run identified by the frozen recovery
manifest. It was codified after that run and after preliminary offline inspection
of its outputs on 2026-10-12. The formulas, labels, persona tiers, score rules,
bootstrap seed, and pass criterion come from frozen v1.0; no thresholds are tuned
here. These results must be named **v1.1 recovered** and must not be represented
as completed frozen v1.0 final metrics.

Before calculation, require all v1.0/v1.1 source locks, the immutable recovery
manifest and source-file hashes, the 90 frozen human labels, all expected case and
persona IDs exactly once, and validated report score arithmetic. The saved raw
`AnswerEvaluation` for every follow-up case must reproduce its saved final route
under the unchanged `resolve_follow_up_decision` policy. Keep the source run's
`incomplete` status and missing per-call/request provenance visible.

## Follow-up decisions

The primary prediction is **InterMind's final route**, not the model's raw
`decision` field. Join saved predictions to frozen human labels by `case_id`.
Positive means `FOLLOW_UP_WARRANTED` for the human and `follow_up` for the
route. Exclude `AMBIGUOUS` human labels from primary TP/FP/FN/TN and report
their count and share. Compute precision, recall, F1, unnecessary follow-up
rate, missed follow-up rate, Wilson precision/recall intervals, and a 10,000
replicate cluster bootstrap F1 interval with frozen seed 401. The cluster key
is `target` plus the original question; multiple candidate answers to one
question stay together. Report the all-warranted and all-not-warranted
ambiguous-label sensitivity results. Use the existing frozen v1.0 metric
function for these calculations.

Separately tabulate raw model decisions and their confusion matrix as a
diagnostic. List every raw-to-route override with its `case_id`, frozen human
label, and before/after confusion category. Do not fold raw decisions into
the primary routed F1 or infer manual error causes from saved scores alone.

## Evaluation discrimination

Use each recovered report's original `overall_score` and recommendation,
validated against the unchanged weighted scoring and recommendation rules.
There must be exactly one strong, mixed, and weak authored persona for each of
the five frozen jobs. Report all 15 scores and recommendations, per-job strict
strong > mixed > weak ordering and margins, tier means and ranges, all three
pairwise Cliff's deltas, weak >= strong overlap, and the frozen gate:
strong/weak delta >= 0.5, weak >= strong overlap <= 0.20, and at least 4/5
jobs strictly ordered. This tests separation on scripted personas; it does
not establish human score accuracy or fair hiring outcomes.

Both analyses are descriptive recovery results from one incomplete source run.
Its per-request payload hashes, returned model IDs, token usage, and complete
per-turn histories were not saved. Dataset and source-code hashes and report
arithmetic support reuse, but cannot reconstruct that missing provenance.
The 90 cases contain question clusters and the 15 persona reports share five
jobs and authored tier assumptions. Publication must disclose these limits.
