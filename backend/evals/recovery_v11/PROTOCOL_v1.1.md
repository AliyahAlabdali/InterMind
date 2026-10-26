# InterMind recovery and targeted latency protocol v1.1

**Version:** 1.1. **Status:** frozen for offline preparation; paid phases require separate approval.
This is an amendment, not a revision of frozen v1.0. The failed v1.0 final run remains
incomplete and produces no v1.0 final metrics. Human follow-up labels were frozen before v1.0
was finalized; this amendment was written after seeing the interrupted run's path counts.
All existing v1.0, pilot, label, and Claim & Score Validity v1.0 locks remain authoritative.

## Recovery scope

The source is `results/20261011T223751Z-final`, which must contain only `progress.jsonl` and
`run_state.json` with status `incomplete`. The read-only audit checks its file hashes against a
write-once manifest, verifies exactly the 90 frozen follow-up IDs and policy decisions, and
validates all 15 frozen persona IDs, five jobs, three authored tiers, 150 exact question/answer
pairs, schemas, overall-score arithmetic, and recommendations. The manifest records frozen
inputs, source code, output IDs, and missing per-call provenance. An ID match does not prove the
lost request payloads or returned model IDs. Do not call this a completed v1.0 run.

Recovered follow-up and discrimination analysis may be produced only under a separately
versioned aggregation tool that reports this provenance gap. No number is released as a final
metric merely because these rows validate. If a recovery check fails, rerun that component in
a fresh versioned run; never edit the source progress file or invent missing records.

## Evidence source attribution

The original per-turn persona histories and `evidence_internal.json` are absent. For each of
the 239 saved report evidence strings, compare its v1.0 classification against each of the
ten frozen candidate answers **individually**. Only a unique exact match to the reported
target answer is `unique_target_exact`. A lexical-only match, a single other-source match,
multiple matches, or no automatic match goes to blind human review. These statuses describe source attribution,
not claim validity or support for a score. The blind review includes the target question,
target answer, and all ten complete answer pairs; it hides tier, score, and automatic status.
The reviewer records the source answer index and `supported`, `unsupported`, or `cannot_tell`
for every unresolved string. Missing per-turn history is never reconstructed as if observed.
The offline inventory has 217 unique exact matches and 22 review cases (4 lexical and 18
without an automatic match). Until every unresolved item is reviewed, no recovered
quotation-fidelity metric is reported.
Any eventual metric must be called **v1.1 recovered report evidence quotation fidelity**,
with its denominator, source limits, review count, and a report-cluster summary. It is not
the frozen v1.0 Evidence Traceability metric. Material claim support and score defensibility
remain a separate study.

## Targeted advance-path latency

The fixture uses all five frozen jobs in sorted `jd_id` order. For each, use the first of its
ten fixed targets. The initial main question is that target's authored question; the prior
main answer is its authored weak answer. The fixed follow-up text is `Give the concrete steps
and validation for {target}.` The measured follow-up answer is its authored strong answer.
These setup turns are a **synthetic benchmark fixture**, not measured model predictions. A
valid LangGraph checkpoint is created at the pending follow-up interrupt. On resume, the
unchanged production graph increments the follow-up count to one, evaluates the answer, and
advances under the unchanged one-follow-up cap. At least nine other targets remain in the plan.
Setup is outside timing and has no API calls. The timed operation is the actual
`POST /interviews/{id}/answers` endpoint through sequential in-process ASGI transport,
including answer evaluation, next-target selection, question generation, repository work,
and response serialization. Network transit and browser render are absent.

**Estimand:** server-side advance-path latency under this follow-up-resolution fixture. It is
not natural production-path latency, initial-answer latency, or browser-perceived latency.
Report the physical client region, environment, date, requested alias, returned model IDs,
repository backend, path counts, sample size, nearest-rank p50/p95/p99, and failures.

The paid feasibility phase is separate: two fixed requests per job, ten endpoint attempts and
30 attempted API calls maximum. All ten must succeed on the advance path without an application
question-generation retry, with two requests for each job and complete response-model and usage
records; otherwise stop and review the fixture before authorizing latency.
Feasibility observations are never in the latency distribution. It requires separate paid
approval and cannot trigger the latency phase automatically.

The latency phase has three predetermined warm-ups for the first three sorted jobs. Then
issue jobs in deterministic cyclic order among those still below quota, targeting **20 usable
requests per job** and **100 total**. Record every started and completed endpoint attempt,
including non-200, errors, path, duration, retry, and warm-up flag. At most 120 endpoint
attempts and 300 attempted OpenAI calls are permitted. SDK transport retries are disabled.
Production question generation may retry once; if it does, count both API attempts and mark
that endpoint request excluded. Never silently reissue a failed request; move to the next
predeclared fixture. Exclude only the three warm-ups, non-advance paths, errors, and requests
with application question-generation retries. Keep all exclusions in the attempt log.
Stop when each job has 20 usable requests, when either cap is hit, or as soon as remaining
requests are fewer than the remaining quota. An incomplete phase reports no p95.

## API accounting and stopping

Every evaluation-only API call inserts a durable `unknown` attempt row before network I/O.
The row stores a unique ID, schema, requested alias, and dated price version. On response it
stores completed status, returned model from the trace when available, actual SDK input/output
and cached-token usage, and estimated USD. Failed calls are recorded as failed, with usage
if the provider supplied it. A hard interruption leaves an `unknown` row: it is never priced
as zero. A completed response without provider usage has unknown cost, not a zero-cost value.
The total attempted-call cap includes completed, failed, and unknown rows and is
enforced before another call. The ledger and request log are independent of final metadata.
OpenAI billing must be reconciled for any failed or unknown call without provider usage.

The price table is the `gpt-4o-mini` model page dated 2026-10-12: $0.15/M input,
$0.075/M cached input, $0.60/M output. It is an estimate from recorded usage, not a
guaranteed spend ceiling. A model/pricing mismatch or missing actual client region blocks
the paid phase. The frozen v1.0 750-call limit remains historical and is never reused here.

## Publication gates

All recovered sources, blind review decisions, and every latency request must pass their
separate checks before v1.1 aggregation. Recovered scores cannot be combined with pilot data
or represented as a single completed v1.0 run. The separate Claim & Score Validity v1.0 tool
refuses an incomplete final run; use only a separately versioned study method retaining its
preselected sample and original one-human workflow. No post-hoc target selection.
