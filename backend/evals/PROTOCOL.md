# InterMind Evaluation Protocol

**Version:** 1.0 · **Status:** frozen · **Frozen:** yes

This document is the registered methodology. Once frozen, nothing here changes without a
version increment and a recorded reason. Thresholds, formulas, dataset composition and sample
sizes are all fixed *before* the baseline runs, so that no number can be chosen after seeing
results.

**Sequence record:** the independent reviewer completed and froze all 90 follow-up labels
before this protocol was finalized. The label lock records
`2026-10-11T21:17:38.572814+00:00` and SHA-256
`5aedb3371a20958cd80e0a9f7a71f359b1edf8c9bc027b70d2196e5e66564238`.
No pilot or final prediction existed at that point. This departs from the originally planned
protocol-before-labels order; it cannot be described as preregistration before labeling.
The present version freezes methods, datasets, and analysis choices before paid baseline runs.

---

## 0. What is being claimed, and what is not

InterMind is evaluated as an end-to-end AI interviewing system. Four distinct properties are
measured, and the case study must keep them distinct because a system can have any one without
the others:

| Property | Question | Metric family |
| :--- | :--- | :--- |
| **Evidence fidelity** | Is cited evidence something the candidate actually said? | §3 grounding |
| **Judgment quality** | Does the evaluator tell good answers from bad ones? | §5 discrimination |
| **Adaptive behaviour** | Does it follow up when a follow-up is warranted? | §4 follow-up |
| **Stability** | Does identical input produce the same verdict? | §6 stability |

**Evidence fidelity is not judgment quality.** A system that quotes candidates perfectly while
scoring them arbitrarily would score well on §3 and badly on §5. Therefore:

> **Gate rule.** No grounding metric may be presented as evidence that InterMind evaluates
> candidates *well* unless the discrimination result in §5 holds. Discrimination is a
> validation gate on the headline metrics, not an optional extra. If §5 fails, §3 may only be
> described as evidence *fidelity* — never as evaluation quality — and the case study must say
> so explicitly.

Out of scope, and never to be claimed: business impact, hiring-time reduction, production
scale, load behaviour, fairness or non-discrimination, speech-to-text accuracy, and any claim
about models other than the one recorded in the run metadata.

---

## 1. Candidate portfolio metrics

Expected to qualify, subject to results. Final selection happens *after* the baseline.

| Metric | Label | Status |
| :--- | :--- | :--- |
| Evidence traceability (variant TBD, §3.6) | `EVIDENCE TRACEABILITY` | Conditional on §5 gate |
| Follow-up decision F1 | `FOLLOW-UP F1` | Conditional on result |
| Server-side turn latency p95 | see §7.3 for the permitted label | Conditional on result |
| Evaluation discrimination | validation gate, §5 | Must be reported beside the other three |

Three defensible numbers are preferred over four with a caveat.

---

## 2. Data separation

Three disjoint pools. **No final metric may include a development or pilot case.**

| Pool | Path | Purpose | API |
| :--- | :--- | :--- | :--- |
| **development** | `datasets/development/` | Validate metric *mechanics* only — the grounding rule's thresholds and guards. Numbers from here are never reported as InterMind performance. | none |
| **pilot** | `datasets/pilot/` | Validate the harness against the real API: trace capture, serialisation, adjudication export, token accounting. Cases are disjoint from evaluation. | ~42 calls for the four-metric implementation; hard cap 80 |
| **evaluation** | `datasets/evaluation/` | The frozen four-metric baseline. Labels frozen before any prediction exists. | ~564 calls if all latency probes advance; hard cap 750 |

Permitted uses of the pilot: verify harness correctness, verify trace capture, discover
implementation bugs, calibrate token usage, estimate cost, confirm result serialisation,
confirm the adjudication export carries sufficient context.

Forbidden uses of the pilot: optimising prompts, tuning InterMind, choosing favourable metrics,
altering final labels, tuning θ, tuning scoring thresholds, tuning follow-up policy.

If the pilot reveals a protocol flaw: revise the protocol, increment the version, regenerate an
untouched evaluation set if the flaw touched it, then freeze.

**The deterministic fake client may never produce a reported number.** It is permitted only for
harness self-tests, and is hard-blocked from writing into `results/`.

---

## 3. Evidence grounding

### 3.1 Unit and source scoping

Unit of analysis: **one evidence string**.

For evidence string `e`, the permitted source set `A(e)`:

- `assessment_method == "direct"` → **every** answer turn in `InterviewState.history` sharing
  that target's `root_question_id` (main answer plus any follow-up answer).
- `assessment_method == "cross_target"` → the single answer turn in which that
  `CrossTargetEvidence` was recorded.

`QuestionEvaluationSummary.candidate_answer` must **not** be used as the source: it holds only
the last turn, while `evidence` accumulates across all turns of the exchange, so scoring
against it would falsely fail legitimate main-answer evidence on every followed-up target.

### 3.2 Normalisation (frozen)

NFKC → casefold → tokenise on `[a-z0-9]+(?:[-+/.#][a-z0-9]+)*\+*#*` (preserving intra-word `-`,
`+`, `/`, `.`, `#`, so `C++`, `CI/CD`, `scikit-learn`, `3.11`, `C#` survive) → drop a frozen
function-word stoplist → no stemming or lemmatisation.

Stemming is deliberately excluded so that any verdict is verifiable by eye. Inflection slack is
absorbed by the threshold instead.

### 3.3 Tiers

```
SUPPORTED_EXACT    normalised e is a contiguous substring of normalised join(A(e))
SUPPORTED_LEXICAL  coverage ≥ θ  AND  bigram_coverage ≥ θ_bigram  AND  no guard fires
AMBIGUOUS          everything else → blind human adjudication (§3.5)
```

```
coverage(e)        = |content tokens of e present in A(e)| / |content tokens of e|
bigram_coverage(e) = |adjacent content-token pairs of e present in A(e)| / |pairs of e|
```

Coverage is **asymmetric by design**: every content token of the *claim* must appear in the
*answer*; the answer may say far more. Bigrams are formed over content tokens so that paraphrase
changing only function words is not punished, while a substituted or inserted content word
always breaks a pair.

### 3.4 Registered constants and guards

| Constant | Value | Chosen how |
| :--- | :--- | :--- |
| `THETA` | **0.90** | Development set only, by a pre-committed rule (§3.4.1) |
| `THETA_BIGRAM` | **0.60** | Development set only |
| `MIN_CONTENT_TOKENS_FOR_LEXICAL` | **4** | Development set only |

Guards — each can only *block* an auto-accept, never promote one. A blocked case is
`AMBIGUOUS`, never `UNSUPPORTED`: this rule does not claim to detect unsupported evidence, only
to decline to vouch for it.

1. `too_short` — fewer than 4 content tokens. Applies to **every tier including exact match**,
   because a one-word string is a substring of any answer that mentions the word once.
2. `negation_present` — evidence contains a negation token. A negated claim and its positive
   form share nearly all content tokens, so coverage cannot separate them and the error is
   maximally consequential.
3. `numeric_mismatch` — a digit-bearing token in the evidence is absent from the answer.
   Quantities are substance, not function words, and get no slack.
4. `adjacency` — `bigram_coverage < 0.60`.

#### 3.4.1 How θ was chosen, and the honest limits of that choice

The decision rule was **pre-committed before the development set was run**: take the lowest
threshold producing **zero false accepts**, where a false accept is auto-accepting evidence a
human would call unsupported. Rationale: a false accept silently inflates a published figure,
whereas over-routing only costs review time.

The data then selected **θ = 0.90**. Results on the 26 development cases:

| θ | False accepts | Correct auto-accepts | Adjudication load |
| :--- | :--- | :--- | :--- |
| 0.70 | 2 | 3 | 81% |
| 0.80 | 2 | 3 | 81% |
| **0.90** | **0** | 2 | 92% |

The adjacency guard was added for the same reason, after unigram coverage alone admitted three
false accepts from one cause — a bag of words loses word order, so evidence can reuse an
answer's vocabulary while changing who did what to which thing (`"moved the checkout service
onto Kubernetes"` scored 1.00 against an answer about the *payment* service; `"the team wrote
the Helm charts"` scored 0.88 against `"I wrote the Helm charts"`, the pronoun being a
stopword). Each rewrite creates a bigram the answer never contains, so adjacency catches all
three. Adding it cut false accepts from 4 to 2; θ=0.90 then removed the last 2.

**Three limitations stated up front:**

- The choice between 0.80 and 0.90 turns on **two development cases**. That is thin. Every
  reported result therefore carries the full sensitivity table at 0.70 / 0.80 / 0.90, so the
  threshold is never load-bearing on its own.
- **92% adjudication on the development set is a safety result, not a load estimate.** That set
  is deliberately adversarial — 23 of its 26 cases are edge cases by construction. Real model
  evidence should be dominated by near-verbatim quotes, since that is what the prompt asks for.
  **Expected adjudication load must be estimated from the pilot**, and the evaluation sample
  sized so that manual load stays tractable (target: ≤ 80 adjudications).
- **Known blind spots**, documented rather than papered over: quantities written as words
  (`"two hundred"` → `"twenty"` is invisible to the numeric guard); reversed causality
  expressed with different adjacencies; attribution shifts where the pronoun is a stopword and
  no bigram breaks. These route to adjudication in the development set only because other
  guards happened to fire. A lexical rule cannot close them; the human tier is what covers them.

### 3.5 Blind adjudication

`AMBIGUOUS` cases export to the run's `evidence_adjudication_blind.csv` as `(evidence_string, full source answer
text)` pairs. **Stripped before export:** coverage and bigram scores, guard reason, persona
label, target, run ID, model output, and anything indicating what the automatic rule concluded.
Order shuffled.

Blinding is required because a coverage score or persona label would anchor the reviewer toward
the classifier's verdict — and the classifier is the thing being audited.

Verdicts: `supported` / `unsupported` / `cannot_tell`.

Criterion: *"Did the candidate say, or clearly and necessarily imply, this?"* Inference beyond
the words — reading competence into a vague answer — is `unsupported`.

`cannot_tell` counts as **unsupported** in all headline figures (conservative) and is also
reported separately.

Full rubric: [`ADJUDICATION_RUBRIC.md`](ADJUDICATION_RUBRIC.md).

Before the final run, manually inspect the pilot's automatically accepted evidence against
its full source answers for context reversals or clipped negation. An exact substring can still
mislead when the surrounding answer qualifies it. Any false accept is a protocol flaw: stop,
version the rule and protocol, and keep the final dataset untouched until re-frozen. This
pilot check is a safety gate, not a performance estimate or a tuning set.

### 3.6 Reported metrics — four, never collapsed

```
automatic verification rate = (EXACT + LEXICAL) / E
adjudicated traceability    = (EXACT + LEXICAL + ADJUDICATED_SUPPORTED) / E
unsupported evidence rate   = (ADJUDICATED_UNSUPPORTED + CANNOT_TELL) / E
adjudication load           = AMBIGUOUS / E
```

Which of these — if any — reaches the portfolio card is **decided after the results**, not now.
Both candidates have known defects: the automatic rate systematically under-credits legitimate
paraphrase (the system explicitly permits paraphrase), while adjudicated traceability depends
on single-annotator human review. If adjudicated traceability is used, its provenance must
state that unresolved cases received blind human review.

`unsupported evidence rate` is reported in every presentation of a traceability figure. It is
never omitted, and traceability is never presented as a single favourable number alone.

---

## 4. Follow-up decision quality

### 4.1 Labels

Human labels only. Produced by the reviewer against
[`FOLLOWUP_RUBRIC.md`](FOLLOWUP_RUBRIC.md), **blind**: the export carries target, question,
answer, and any context genuinely needed to judge — and carries no InterMind prediction, no
author-intended label, no category name, no score, no generated follow-up, and no failure
classification.

Label values: `FOLLOW_UP_WARRANTED`, `NO_FOLLOW_UP_WARRANTED`, `AMBIGUOUS`.

**Handling of `AMBIGUOUS`, fixed in advance:** excluded from the primary precision/recall/F1
computation, with the count and share reported alongside. A secondary sensitivity analysis
reports F1 under both forcings (all ambiguous → warranted, all → not warranted) to bound the
effect. Ambiguous cases are never silently dropped or quietly resolved by the author.

No separately sealed author-intent file exists. No construction-intent comparison or second
annotation is claimed. The frozen human labels are the sole reference standard.

### 4.2 Formulas

With `y` = human label and `ŷ` = `resolve_follow_up_decision(...).decision == FOLLOW_UP`:

```
precision = TP / (TP + FP)
recall    = TP / (TP + FN)
F1        = 2·precision·recall / (precision + recall)
unnecessary follow-up rate = FP / (TN + FP)
missed follow-up rate      = FN / (TP + FN)
```

A full 2×2 confusion matrix is always reported with counts.

### 4.3 Error attribution

Enabled by `resolve_follow_up_decision` being a pure function of the evaluation. For each error,
the raw `AnswerEvaluation` is re-inspected *before* the policy ran:

| Condition | Attribution |
| :--- | :--- |
| FN, `follow_up_question` empty | **LLM judgment failure** — no question to route on |
| FN, `follow_up_question` populated | **Policy failure** — score band, `weaknesses` gate, or cap suppressed it |
| FP, nothing worth asking per reviewer | **LLM over-generation** |
| FP, question reasonable but premature | **Policy failure** — band fired too eagerly |

Reported as a separate table. Never folded into F1.
This is a manual post-run review of the saved raw evaluations and human labels; the
aggregator does not infer the attribution or alter the confusion matrix.

---

## 5. Evaluation discrimination (validation gate)

Three personas (strong / mixed / weak) × 5 job descriptions. Construction rules in
[`datasets/evaluation/personas.py`](datasets/evaluation/personas.py); summary:

- **Strong** — specific systems, named trade-offs, quantities, admitted limitations.
  **Must not simply enumerate the JD's keywords**; where possible demonstrates competency
  through a described decision rather than by naming the technology.
- **Mixed** — genuinely strong on 3–4 targets, genuinely thin on 3–4, including at least one
  confident-but-wrong answer. An uneven real candidate, not an artificial midpoint.
- **Weak** — fluent, cooperative, plausible, substantively empty: generalities, deflection to
  team accomplishments, tutorial-level description. **Never incoherent.**

Written against JD targets only, never against the evaluation prompt's rubric.

```
Cliff's δ(X,Y) = (#{x>y} − #{x<y}) / (n_x · n_y)      for strong/mixed, mixed/weak, strong/weak
overlap        = #{(x,y) : y ≥ x} / (n_x · n_y)       weak ≥ strong pairs
ordering consistency = |{jd : mean(strong) > mean(mixed) > mean(weak)}| / 5
```

Plus the recommendation distribution per persona.

**Gate criterion, fixed in advance:** the gate passes if `δ(strong, weak) ≥ 0.5` with
`overlap ≤ 0.20`, and ordering consistency ≥ 4/5. If it fails, §0's gate rule applies.

---

## 6. Stability

### 6.1 Why fixed-turn replay, not full interviews

An "identical transcript" cannot be re-run through the full graph: the graph's path depends on
the LLM's own follow-up decisions, so reruns diverge into different question sets and the inputs
stop being identical.

Stability therefore replays **fixed turn tuples** `(question, answer, target, prior_exchange)`
through `AnswerEvaluationService`, then feeds the resulting evaluations through the untouched
deterministic `report_scoring`. Inputs are byte-identical across repetitions; the only varying
quantity is the LLM sample.

### 6.2 Configuration

The shipped configuration, unchanged: **temperature unset (API default)**, model as recorded in
run metadata, prompts and thresholds untouched. Temperature is not modified before the baseline.

### 6.3 Formulas

```
per-answer score SD_i    = sd(s_i,1..R)                    report mean and max over i, and SD-of-SD
overall-score MAD_j      = mean_r |o_j,r − median_r(o_j)|
recommendation agreement = (1/J) Σ_j (count of modal recommendation in R runs) / R
recommendation flip rate = |{j : distinct recommendations > 1}| / J
boundary distance_j      = |median_r(o_j) − nearest derive_recommendation boundary|
```

Variance decomposition: LLM evaluation is the only stochastic source; `compute_overall_score`
and `derive_recommendation` are pure. Verified by a determinism assertion on fixed inputs, at
zero API cost.

Every flip is classified **boundary-adjacent** (`boundary distance < sd_r(o_j)`) or **genuine
inconsistency**. A 0.002 drift across a threshold is not the same defect as a 0.3 scoring swing.

### 6.4 Presentation rule

**Recommendation agreement is never reported alone.** Every presentation pairs it with
continuous score deviation and boundary proximity, because a high agreement percentage can hide
substantial score variation that happens to stay on one side of a threshold, and a trivial
variation near a boundary can manufacture a flip.

`RECOMMENDATION STABILITY` may appear on the card **only if** the continuous metrics show the
shorthand is not misleading — specifically, mean per-answer score SD is small enough that
agreement is not an artefact of threshold placement. If that condition fails, the metric moves
to the case study with both numbers shown.

If the baseline proves unstable, the temperature experiment becomes a separate, clearly
labelled before/after improvement. **The baseline is never retro-fitted.**

---

## 7. Latency

### 7.1 What the architecture actually does

`POST /interviews/{id}/answers` performs, in one request: a rate-limit check; the graph resume
(answer evaluation, and on the advance path question generation); two repository reads for the
candidate; a plan read and an activity **write**; then response serialisation.

So **summing LLM stage durations understates the candidate-visible wait.** Deterministic
orchestration and database work sit inside the same request.

### 7.2 Measurement

Two separate tables, never pooled:

1. **Per-stage LLM latency**, from the existing `TraceRecorder.duration_seconds` grouped by
   `schema` name — `JobSpec` (JD analysis), `GeneratedQuestionSet` (question generation),
   `AnswerEvaluation` (answer evaluation), `ReportNarrative` (narrative).
2. **Server-side request wall-clock**, measured by driving the real HTTP endpoint in-process
   (ASGI transport) and timing the full round trip. This captures orchestration, database work
   and serialisation, and requires **no application code change**.

Deterministic local latency (O\*NET match, p95 6.8 ms) is reported in its own table.

### 7.3 Permitted label

The card metric, if used, is the **server-side wall-clock of the answer-submission request on
the advance path** — the path that includes question generation and is the slower, more common
case.

It may **not** be labelled "next-question latency" or anything implying total user-perceived
time, because browser network transit and frontend render are excluded. Permitted labels:
`TURN LATENCY P95` or `API TURN P95`, with provenance stating server-side, in-process,
sequential, excluding browser transit. The exact label is chosen after the traces confirm what
was timed.

### 7.4 Controls

3 discarded warm-up calls; strictly sequential issuance (concurrency would measure OpenAI
queueing, not user experience); a single contiguous session with start/end timestamps; retries
excluded from the distribution but counted and reported. Nearest-rank percentiles. p99 only
when n ≥ 100. The four-metric implementation takes 100 usable advance-path samples from
separate two-target in-memory interviews. Each measured answer request evaluates the answer
and generates the next question. Three earlier answer requests are discarded as warm-up.

Disclosed with every figure: model ID, sample size, sequential issuance, date, client
environment and region, and repository backend (in-memory vs PostgreSQL). **This measures the
measurement environment as much as InterMind**, and is reported as such.

---

## 8. Identity invariance (limited robustness probe)

2 transcripts × 3 identity variants × 3 repetitions. Variants alter **only** candidate first
name and pronouns where they occur in the turn payload; technical content byte-identical. Name
sets vary along gender and apparent linguistic origin, enumerated in the dataset file.

```
Δscore_i                   = max over variant pairs |s_i,v − s_i,v'|
evidence stability         = Jaccard(evidence set_v, evidence set_v')
recommendation change rate = |{transcripts with ≥2 distinct recommendations}| / J
```

**Required control.** At the shipped temperature, identical inputs already produce different
scores. An identity-induced delta is meaningless unless it exceeds same-input rerun variance, so
the probe uses the same repetition count as §6 and `Δscore` across identity variants is compared
against `Δscore` across identical repetitions. Without this control the experiment would measure
sampling noise and call it identity sensitivity.

**Permitted claim:** "identity invariance under the tested transformations", with a Wilson
interval and the transformations enumerated. **Never** fairness, unbiasedness, bias-free, or
proof of non-discrimination. Expected to be a case-study metric, not a card metric; if the
sample cannot support a useful interval, it stays in the case study.

---

## 9. Token usage and cost

Instrumentation authorised and implemented: capture
`completion.usage.{prompt_tokens, completion_tokens}` plus cached input tokens into the existing
trace record; aggregate per stage and for the run; price from a dated table with model and pricing
date stated inline, since pricing changes. Actual SDK usage only — never estimated from text
length. The evaluation client disables SDK transport retries so a hidden retry cannot enter the
latency distribution; the application's bounded question-generation retry is counted and its
request excluded from latency.

Supporting metric.

---

## 10. Engineering reliability

Audited, not claimed loosely:

| | Backend | Frontend |
| :--- | :--- | :--- |
| Executed cases | 693 | 241 |
| Declaration sites / functions | 602 | 210 (200 plain + 10 `it.each`) |
| Split | 451 unit / 242 integration | 27 files, 1 jsdom env, 0 skipped |

Total **934 executed cases** from **812 declaration sites**. `vitest list` does not expand
`it.each`, which is why a declaration count understates frontend execution.

**"934 tests" must never appear unqualified**; the unit has to be named.

**No CI quality gate exists.** The single GitHub workflow deploys to Azure and runs neither
tests nor lint. No CI claim may be made. Adding CI is a separate improvement, after baseline.

Supporting metric.

---

## 11. O\*NET retrieval (component-level, internal)

Retained because it surfaced real engineering findings; **demoted** to component-level. Not a
portfolio-card metric.

The existing 30-case dataset is marked **PROVISIONAL**: n=30, imperfect category balance
(software 8, business 6, healthcare 5, engineering 4, data 3, creative 2, education 1,
hospitality 1), author-written examples and labels, three labels widened *after* predictions
were observed, 9 of 30 carrying multi-code acceptable sets, and no real job postings.

Wilson 95% CI on success@1 is **[19.2%, 51.2%]** — too wide for any portfolio claim.

Retained diagnostics: success@1/@3/@5/@10 (**"success@k", never "accuracy"**), MRR, rank
distribution, field ablations, retrieval latency, confidence intervals.

**Retrieval must not be tuned against this dataset and the result then presented as
generalisation performance.**

---

## 12. Statistical treatment

| Quantity | Method | Why |
| :--- | :--- | :--- |
| All proportions (traceability, unsupported rate, follow-up rates, recommendation agreement, identity invariance) | **Wilson score interval, 95%** | Correct near 0 and 1 where the normal approximation fails |
| Precision, recall | Wilson on each | Both are proportions |
| **F1** | **Bootstrap percentile CI, 10,000 resamples over 38 target/question clusters** | Several answers share a question; resampling individual answers would understate dependence. |
| Score SD / MAD | Point estimate + SD-of-SD | Honest about R=5 |
| Persona separation | Cliff's δ + overlap | Non-parametric; no normality assumption on bounded scores |
| Latency | Nearest-rank percentiles, n stated | No distributional assumption |

Nothing more elaborate. **Every reported proportion carries its numerator and denominator
inline.** A percentage from 10 examples is not a percentage from 300.

These are scripted, purposively written cases and reports, not a random sample of real
applicants. Intervals describe resampling uncertainty within this benchmark, not population
performance. Wilson intervals for evidence strings do not account for multiple strings from
one report; treat them as descriptive bounds, not independent-sample inference.

---

## 13. Reproducibility

Every run writes `results/<utc-timestamp>/metadata.json` recording: git SHA, dataset version,
protocol version, model ID, temperature and model settings, timestamp, sample size, API call
count, repository backend, and evaluation configuration. `results/` is immutable; a re-run
creates a new directory.

---

## 14. Mandatory sequence

1. Define claim · 2. Define metric · 3. Define dataset · 4. Define rubric ·
5. **Freeze protocol** · 6. Reviewer approves · 7. Reviewer labels blind · 8. Freeze labels ·
9. Pilot (harness only) · 10. **Run baseline unchanged** · 11. Record baseline ·
12. Diagnose · 13. Propose improvements · 14. Approval · 15. Implement ·
16. Re-run the *same* frozen evaluation · 17. Report before vs after.

**Actual sequence deviation:** step 7 (blind human labeling) and step 8 (label freeze) were
completed before step 5 (protocol freeze). The rubric and labels are preserved unchanged;
this v1.0 freeze occurs before pilot and final paid runs. Reports must disclose this deviation.

Forbidden at every stage: tuning against the evaluation set; cherry-picking; removing failures;
adjusting thresholds after seeing results; modifying prompts, scoring thresholds, follow-up
policy, retrieval or temperature before baseline.

**The current system is the baseline.**

---

## 15. Threats to validity

1. **The author writes the inputs.** Mitigated by blind reviewer labelling (§4.1, §3.5), not
   eliminated.
2. **Single human annotator.** No genuine inter-annotator agreement is available. Author
   construction intent is *not* a second annotation and is never reported as one. Stated as a
   limitation.
3. **Scripted answers are not real candidates** — no speech-to-text disfluency, no adversarial
   behaviour. The ceiling on external validity.
4. **Single model.** Results describe the recorded model only.
5. **High traceability is necessary but not sufficient** for "evidence-based" — hence the §0
   gate.
6. **θ rests on two development cases.** Mitigated by pre-registration and the sensitivity
   table.
7. **Known lexical blind spots** (§3.4.1) are covered only by the human tier.
8. **Small n** for stability (R=5) and identity invariance.
9. **Replay design** (§6.1) does not exercise the adaptive path; full-graph runs cover it
   separately.
10. **Latency reflects the measurement environment**, including repository backend and client
    network.
11. **Speech is excluded entirely** — no claim about the voice path.
12. **Adjudication load is estimated from the pilot**, not from the development set, whose load
    figure is adversarial by construction.

---

## 16. Four-metric implementation

The requested baseline implements §§3, 4, 5, and 7. Stability and identity probes remain in this
broader protocol but are not run or claimed in this baseline. This is why the old ~740-call
whole-protocol estimate has been replaced by the explicit four-metric budget above.

- **Follow-up:** 90 blinded, shuffled cases. The independent reviewer fills only `label` in
  `labels/followup_blind.csv`. The runner refuses final predictions until all 90 labels are
  valid and `freeze-labels` records the CSV's SHA-256 and a read-only frozen copy. A changed
  CSV or frozen copy invalidates the lock.
  The prediction is the unchanged `resolve_follow_up_decision` output. A prior exchange counts
  against its one-follow-up cap, as it does in production.
- **Discrimination and evidence:** 5 job descriptions × 3 scripted personas × 10 common targets
  = 150 fixed answer evaluations. Each target is evaluated once using the shipped prompt and
  model; the shipped report service produces 15 reports. Fixed questions keep target coverage
  identical across tiers. This measures the evaluator/report score on comparable scripted
  answers; it is not a claim about the adaptive question-selection path. Evidence statements
  are extracted from those actual reports. Direct evidence is checked against all direct
  candidate answer turns for its target; cross-target evidence is checked against the original
  candidate answer, never the synthesized cross-target note.
- **Latency:** 100 valid advance-path `POST /interviews/{id}/answers` requests, plus 3 warm-up
  requests, using `httpx` ASGI transport and real route, graph, repositories, and response
  serialization. Interview creation and token setup are outside the timed request; the real
  candidate-token authorization check is inside it.
  A two-target plan ensures a successful first-answer advance generates the next question.
  Follow-up, terminal, warm-up, and retried requests are excluded and counted separately.
- **Expected calls:** final 90 follow-up + 150 persona answer + 15 report narrative +
  103 × (first question generation + timed answer evaluation + next question generation)
  = **564** if every latency probe advances. Pilot: 6 + 15 + 3 + 6 × 3 = **42**. Extra
  latency sessions and bounded question retries can raise these counts. The runner stops at
  80 pilot or 750 final attempted calls and retains partial output if it fails.
- **Reproducibility:** results record the configured and returned model, actual SDK token usage,
  current dated price table, prompt/code/dataset/protocol hashes, git SHA and dirty flag,
  UTC times, raw decisions, report data, evidence mappings, and each request duration.
  A failed run is never aggregated into final metrics. The fake client is used only by
  offline tests and cannot enter `results/` through the paid runner.

`PROTOCOL.lock.json` records this version's SHA-256 plus hashes of the two rubrics, the four
final dataset source files, and the frozen human labels. Both paid commands check that lock
before contacting OpenAI. A protocol or final-dataset edit after the pilot therefore blocks
further execution until it is explicitly versioned and frozen again.
