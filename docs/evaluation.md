# Evaluation

This document separates deterministic offline retrieval/grounding measurements from historical
OpenAI experiments. The commands below use the tracked `onet_kb.jsonl` artifact without an API
key, network, or model calls. Timing depends on the machine. Historical model results have a
different scope and require private retained inputs for full offline reproduction.

```bash
cd backend
python -m evals.run_retrieval_eval     # occupation retrieval: success@k, A/B, latency
python -m evals.diagnose_retrieval     # why it misses: rank distribution, taxonomy, ablations
python -m evals.run_grounding_eval     # the grounding gate: what reaches the interview
python -m evals.run_gate_metrics       # the gate as a classifier: P/R/F1/MCC, threshold sweep
```

All four accept `--json <path>` to emit machine-readable results.

## A note on which metrics apply

Picking one occupation out of 1,016 is a **ranking** task with a single right answer. Precision@1,
recall@1 and accuracy therefore all collapse onto one quantity — the share of cases whose top
result was acceptable — and an F1 of that number with itself is the same number again. Reporting
them as three figures would imply three independent measurements where there is one. For this
shape of problem the informative metrics are **success@k** (called recall@k below, as is
conventional for known-item retrieval), **MRR**, and the **rank distribution**.

Precision, recall and F1 *do* apply to the grounding gate, which makes a real binary decision
(use this match, or abstain) against a real binary truth (was the match acceptable). Those are
reported in full, with MCC alongside, because the classes are unbalanced — 20 of 30 matches are
wrong — and both accuracy and F1 flatter a classifier on an unbalanced set in ways MCC does not.

## What is and is not measured

The production path is `JD text → (LLM) → JobSpec → (TF-IDF) → occupation → interview plan`. These
harnesses supply the `JobSpec` directly, so they isolate everything *after* extraction. That makes
them deterministic and free to run, and it means they say nothing about:

- how faithfully the LLM extracts a `JobSpec` from raw prose,
- the quality of generated questions, follow-up decisions, or report narratives,
- end-to-end request latency, which is dominated by the LLM calls either side of retrieval.

Those are outside the offline retrieval harness. The historical evaluation below measures selected
follow-up, evidence, discrimination and server-side latency outcomes. The 6.8 ms figure later in
this document remains a historical local retrieval measurement, not answer-endpoint latency.

## Historical OpenAI evaluation

The original v1.0 final run was interrupted. Retained outputs and subsequent recovery experiments,
including a separate v1.1 latency run, produced the following results. They are **not measurements
of today's production deployment**, and no new paid evaluation was run for the October 27 audit
or remediation. See the [protocol](../backend/evals/PROTOCOL.md),
[results summary](../backend/evals/results_summary.md), and
[historical provenance](../backend/evals/recovery_v11/HISTORICAL_PROVENANCE_v1.2.md).

| Metric | Retained result | Scope and acceptance |
|---|---|---|
| Evidence traceability | **239/239 supported evidence strings** across 15 reports | 217 automatic matches and 22 human adjudications; evidence-string fidelity, not correctness of every report claim or score. No separate numerical acceptance threshold was established. |
| Follow-up F1 | **0.8852459**, 90 cases; TP 27, FP 3, FN 4, TN 56 | Frozen human labels: 31 warranted / 59 not warranted. Primary metric includes routing policy, not only raw model decisions. No separate F1 acceptance threshold was established. |
| Next-question server-side P95 | **3.834 s**, 100 usable requests | Nearest-rank P95 from the retained sequential ASGI experiment with live model calls, in-memory repositories and three excluded warmups. Excludes browser/network rendering, production PostgreSQL, and Vercel cold starts; not a production latency SLO. |
| Discrimination gate | **Passed** | 15 scripted personas across five JDs; strong/mixed/weak means 0.85212 / 0.58146 / 0.21808, strong–weak Cliff's delta 1.0, overlap 0, correct ordering in 5/5 JDs. Gate: delta ≥0.5, overlap ≤0.2, ordering ≥4/5. |
| Recommendation stability | **Explicitly deferred** | Repeated-run experiments were not executed. No stability result or acceptance claim. |

The personas supply fixed answers for ten targets each; this is not an observed population of
applicants or a browser-driven adaptive interview study. One human finalized the reviews with AI
assistance; there was no independent blinded second reviewer. The retrospective claim/score review
is distinct from the 239 evidence strings: 221/245 claims were fully supported, 18 partially
supported and six unsupported; 44/45 score judgments were defensible. Do not relabel evidence
fidelity as perfect report accuracy. These experiments establish neither hiring accuracy nor
fairness or predictive validity.

The interrupted v1.0 run lacks complete original per-call provenance. Recovery authenticates
retained bytes and historical source snapshots; it cannot reconstruct missing API metadata or
turn historical results into measurements of current code. Frozen datasets, reviews, raw outputs
and recorded metrics are preserved. Public code and aggregate results are available, but raw
answer-bearing inputs remain private. With the authorized bundle restored, run
`python -m evals.private_history --check-only` from `backend/` to check integrity offline.
Live runners incur OpenAI charges and require approval; do not rerun them for a documentation check.

## Offline retrieval and grounding

## Dataset

30 labelled job descriptions in [`backend/evals/retrieval_dataset.py`](../backend/evals/retrieval_dataset.py),
spanning software, data, healthcare, business, engineering, creative, education and hospitality —
chosen to exercise the full 1,016-occupation knowledge base, not just the technical corner of it.

Each case was written as a realistic posting in the author's own words, deliberately **not** by
paraphrasing the target occupation's O\*NET description or task list; the corpus is matched against
title + description + technologies + core tasks, so reusing that text would measure string identity
rather than retrieval.

Ground truth is a *set* of acceptable SOC codes, because real postings straddle O\*NET's boundaries.
Two rules keep that set from becoming a way to manufacture a better score, and both were applied to
every case before any result was read:

- **Same-family variants count.** `13-1081.00` Logisticians, `.01` Logistics Engineers and `.02`
  Logistics Analysts are one family; so are `17-2112.00` Industrial Engineers and `.03`
  Manufacturing Engineers.
- **Credential-level variants do not.** Technologist, technician, assistant and aide occupations are
  excluded even when they are the nearest neighbour — Physical Therapist Assistants is not a hit for
  a Physical Therapist posting. Collapsing those would hide exactly the confusion a hiring tool must
  not make.

21 of the 30 cases carry a single acceptable code. **Limitation:** this is an author-constructed set
labelled by one person with no inter-annotator agreement. It is sized to detect large regressions and
to compare retriever variants against each other, not to certify an absolute accuracy figure.

## Occupation retrieval

| Metric | Value |
| :--- | :--- |
| Knowledge base | 1,016 occupations |
| Index build (TF-IDF fit, at startup) | ~650 ms |
| recall@1 | 33.3% (10/30) |
| recall@3 | 60.0% (18/30) |
| recall@5 | 86.7% (26/30) |
| MRR | 0.519 |

**recall@1 is low and that is the honest headline for this stage.** A deterministic TF-IDF match
over 1,016 occupations picks the single best occupation in a third of cases. The correct occupation
is usually *present* — 86.7% within the top 5 — but it frequently is not first. Characteristic
failures: a Frontend Engineer posting matching Librarians and Media Collections Specialists, a
Veterinarian posting matching Animal Control Workers, a Technical Writer posting matching
Architectural and Engineering Managers. Absolute cosine scores are low throughout (0.07–0.29),
which is itself the signal that query and corpus representations are only loosely aligned.

### Why it misses

`python -m evals.diagnose_retrieval` asks for the full 1,016-deep ranking rather than stopping at
5, which changes the diagnosis materially:

| recall@1 | @3 | @5 | @10 | @20 | @50 | median rank | mean | worst |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 33.3% | 60.0% | 86.7% | 96.7% | 96.7% | 100% | **2.0** | 3.5 | 22 |

**The correct occupation is never actually lost — its median rank is 2.** So this is a ranking
*calibration* problem, not a failure to represent occupations. That matters because the two have
completely different fixes.

The score gaps confirm it. On a scale where top-1 scores span only 0.071–0.292 (median 0.130), the
median gap between the returned top-1 and the correct occupation is **0.028** — roughly a fifth of a
typical score. The top few candidates are near-ties, so small representation changes reshuffle them.

Classifying all 20 misses by their SOC relationship to the correct answer:

| Error class | Cases |
| :--- | :--- |
| Credential / seniority sibling (Physical Therapist **Assistants**, Industrial Engineering **Technologists**, Public Relations **Managers**) | 3 |
| Same SOC major group — right sector, wrong occupation | 7 |
| Unrelated major group | 10 |

The credential siblings are the most explainable class: those occupations share almost all of their
vocabulary with the target, and what distinguishes them — credential level and seniority — is carried
by one or two words against several hundred.

### The dominant cause, measured

Removing each query field in turn and re-scoring isolates what is actually hurting:

| Query variant | recall@1 | recall@5 | Δ recall@1 |
| :--- | :--- | :--- | :--- |
| Full query (shipped) | 33.3% | 86.7% | — |
| **without `responsibilities`** | **43.3%** | 86.7% | **+10.0 pp** |
| without `skills` | 36.7% | 80.0% | +3.3 pp |
| without `competencies` | 36.7% | 83.3% | +3.3 pp |
| without `seniority` | 33.3% | 86.7% | +0.0 pp |
| without `summary` | 33.3% | 83.3% | +0.0 pp |
| without `competency_descriptions` | 26.7% | 86.7% | −6.7 pp |
| without `role_title` | 23.3% | 76.7% | −10.0 pp |

**The responsibilities block is actively hurting retrieval: dropping it gains 10 points of
recall@1.** `_jobspec_to_query_text` concatenates every field into one bag of words, so four
sentences of duties contribute far more term mass than the role title — and those sentences are full
of generic verbs (*design, build, maintain, review, coordinate*) that match many occupations weakly
rather than one strongly. The title and the competency descriptions are the fields that carry real
signal; both hurt when removed.

So the concrete fix is not necessarily embeddings: it is **field weighting** — scoring the title and
competency descriptions more heavily than the responsibilities prose, or querying the fields
separately and combining the rankings. That is a far cheaper change than replacing the retriever, and
the harness now exists to check whether it works. Embedding-based retrieval remains the longer-term
option, and would also address the credential-sibling class, which no amount of lexical reweighting
will separate.

### Latency

Per-call wall-clock time for `match_jobspec`, over 600 timed queries (20 trials × 30 cases):

| mean | p50 | p95 | p99 | max |
| :--- | :--- | :--- | :--- | :--- |
| 6.2 ms | 6.0 ms | 6.8 ms | 7.2 ms | 7.9 ms |

Retrieval is in-process and CPU-bound against a pre-fitted matrix, so the distribution is tight.
Measured on Python 3.12.10, Windows 11. This is retrieval only — not end-to-end request latency.

### The fragment-downweighting A/B

`onet_kb.FRAGMENT_WEIGHT` documents a real failure: query-side redundancy (`computer vision` +
`vision` + `computer`) once let a Computer Vision Engineer posting match **Orthoptists**, a clinical
eye-care occupation. The fix downweights a query unigram already covered by an active query bigram.
Scoring the dataset with the fix on (0.5) and off (1.0):

| FRAGMENT_WEIGHT | recall@1 | recall@5 | MRR |
| :--- | :--- | :--- | :--- |
| 1.0 (off) | 33.3% | 86.7% | 0.527 |
| 0.5 (shipped) | 33.3% | 86.7% | 0.519 |

**The fix is aggregate-neutral: +0.0 pp on recall@1, and marginally worse on MRR.** It repairs two
cases (`bookkeeper`, `chef`) and regresses two (`database-administrator`, `industrial-engineer`).

It does, however, do what it was written to do on the failure class it was written for. Top results
for the Computer Vision posting:

| Rank | Weight 1.0 | Weight 0.5 |
| :--- | :--- | :--- |
| 1 | Data Warehousing Specialists | Data Warehousing Specialists |
| 2 | Database Architects | Computer Hardware Engineers |
| 3 | Computer Hardware Engineers | Database Architects |
| 4 | Operations Research Analysts | **Robotics Engineers** |
| 5 | Model Makers, Wood | Model Makers, Metal and Plastic |

With the fix off, no robotics or vision occupation appears in the top 8 and the list degenerates into
noise (*Model Makers, Wood*; *Industrial Truck and Tractor Operators*). With it on, Robotics
Engineers enters at rank 4 and Robotics Technicians and Remote Sensing Technicians follow.

So the honest reading is narrower than the docstring implies: the fix redirects a specific class of
phrase-fragment failure toward the right domain without improving aggregate accuracy. Keeping it is
justified by that behaviour, not by the summary metrics — and the value of having the harness is that
it says so rather than letting the anecdote stand in for a result.

## The grounding gate

Because retrieval is often wrong, the question that matters for a hiring tool is not "how often is
retrieval right" but **"when the system acted on retrieval, was retrieval right"** — and how reliably
it refuses to act when retrieval is wrong. `InterviewPlannerService` gates all O\*NET context behind
`_match_is_grounded`: an absolute score floor plus a core task that actually resembles the job.

| Outcome | Cases |
| :--- | :--- |
| Match acceptable, context used | 9 |
| Match wrong, context used | 13 |
| Match wrong, context suppressed (gate working) | 7 |
| Match acceptable, context suppressed (conservative miss) | 1 |

| Metric | Value |
| :--- | :--- |
| Grounding rate | 73.3% (22/30) |
| Grounding precision | 40.9% (9/22) |
| Abstention recall | 35.0% (7/20) |

**The macro gate alone does not hold.** It passed 13 of 20 wrong matches. Stated plainly: the score
floor and best-task-relevance check are not sufficient to separate right from wrong occupation picks
on this dataset, and the thresholds were calibrated against a handful of hand-checked examples rather
than against a labelled set like this one.

### The gate as a classifier

`python -m evals.run_gate_metrics` scores that decision properly. Positive = "use this match".

|  | Match correct | Match wrong |
| :--- | :--- | :--- |
| **Used context** | 9 (TP) | 13 (FP) |
| **Abstained** | 1 (FN) | 7 (TN) |

| Precision | Recall | Specificity | F1 | Balanced acc. | Accuracy | MCC |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 40.9% | 90.0% | 35.0% | 56.3% | 62.5% | 53.3% | +0.267 |

The shape of the error is clear: **recall 90%, specificity 35%.** The gate almost never blocks a
correct match — and almost never blocks a wrong one either. It is tuned permissively, so it functions
less as a filter than as a formality.

### Can it be fixed by retuning?

The gate's load-bearing signal is the best TF-IDF relevance of the matched occupation's core tasks to
the JobSpec. Treating that as a score and sweeping the threshold across its entire range:

| | |
| :--- | :--- |
| ROC-AUC | **0.600** (0.5 = no separating information) |
| Average precision | 0.385 (base rate 0.333) |
| Best achievable F1, any threshold | 60.0% at 0.1074 (shipped: 56.3% at 0.10) |
| Best achievable MCC, any threshold | +0.350 at 0.1074 (shipped: +0.267) |

**No. Retuning buys about four points of F1 and the ceiling is low because the signal is weak.** An
ROC-AUC of 0.600 on 30 cases means best-task-relevance barely distinguishes a correct occupation from
a wrong one. The shipped threshold of 0.10 is close to the best available cut point already — so the
constant is not mistuned, the signal is simply not discriminative enough to carry the gate.

This is the most useful thing the harness produced. The docstring behind
`_MIN_GROUNDING_TASK_RELEVANCE` reports that best-task-relevance separated its hand-checked wrong
matches (0.036–0.060) from its correct ones (0.120–0.156) cleanly. On 30 labelled cases that
separation does not generalise. The fix is a different signal — title-level agreement, or the
retrieval score margin computed after the field weighting described above — not a different number.

### What actually reached the interview

`onet_grounding_used` only means a context block was assembled. The current planner selects
competencies, technologies and tasks from the JobSpec only. O\*NET may annotate an existing item
as `EvidenceSource.BOTH`; it cannot introduce a new requirement through these selectors.

| Metric | Value |
| :--- | :--- |
| Legacy wrong-match provenance count (ONET or BOTH) | **3/30** cases; includes corroboration, not proof of new requirements |
| Legacy wrong-match count without ONET/BOTH annotations | 10 cases |
| Legacy task annotation count from wrong occupations | **0** |

The legacy annotations were technologies in `frontend-engineer` (one), `devops-engineer` (one),
and `graphic-designer` (two). Calling these three cases "requirement leakage" was incorrect:
`BOTH` corroborates a technology already named in the JD.

The corrected harness uses metric version 2: requirement leakage counts **ONET-only** technologies
and tasks from a wrong occupation, while a separate count reports corroborated JD items (`BOTH`).
This is a provenance-based plan check, not a semantic assessment of question wording. Original
recorded outputs are not rewritten; old JSON fields that combined ONET and BOTH must be interpreted
under their original definition. No planner or model behavior changed to make the metric improve.

An offline rerun on October 27, 2026 with the corrected harness found **0/30 cases with ONET-only
requirement leakage**, and three wrong-match cases corroborating four existing JD technologies.
The gate confusion matrix remained 9 / 13 / 7 / 1. This is a corrected measurement of provenance
on the same deterministic inputs, not a new model evaluation or improved retrieval performance.

**Limitation.** A correct abstention is *safe*, not *accurate*: this measures that bad context is
withheld, not that the resulting interview is good. The context block itself still reaches the
question generator in all 22 grounded cases and can influence question phrasing, which this
harness does not score.

## Summary

| | |
| :--- | :--- |
| Occupations indexed | 1,016 |
| Retrieval success@1 / @5 / @10 | 33.3% / 86.7% / 96.7% |
| Median rank of the correct occupation | 2 |
| Retrieval latency p95 | 6.8 ms |
| Index build at startup | ~650 ms |
| Largest single accuracy lever found | dropping `responsibilities` from the query: +10.0 pp |
| Grounding gate precision / recall / F1 | 40.9% / 90.0% / 56.3% (MCC +0.267) |
| Gate signal separability (ROC-AUC) | 0.600 |
| Legacy wrong-match annotation count, including JD corroboration | 3 of 30 cases; not new-requirement leakage |
| Legacy wrong-match task annotation count | 0 |
| October 27 audit test baseline (unrelated to evaluation quality) | 842 backend + 242 frontend = 1,084 passed |
| October 27 local remediation verification | 850 backend + 242 frontend = 1,092 passed, plus three backend subtests |

### Optional retrieval research, outside final production sign-off

1. **Weight the query fields.** Dropping `responsibilities` alone is worth +10 pp recall@1; weighting
   rather than dropping should do better without losing the cases where duties are the only signal.
2. **Replace the gate's signal.** Retuning the threshold is worth ~4 points of F1 and no more
   (ROC-AUC 0.600). Title-level agreement or a post-reweighting score margin are the candidates.
3. **Keep corroboration separate from new requirements** when interpreting grounding results;
   the historical three-case count does not justify changing planner behavior.
4. **Then consider embeddings**, which are the only approach likely to separate the credential-sibling
   class (Physical Therapist vs Physical Therapist Assistants).
