# Claim & Score Validity recovery compatibility v1.1

**Version:** 1.1. **Status:** preparation only; no human review or result authorized.

The frozen `claim_validity/PROTOCOL_v1.md`, `RUBRIC_v1.md`, `SAMPLE_v1.json`,
`study.py`, and `STUDY.lock.json` remain untouched. The v1.0 study explicitly rejects an
incomplete final run. Its tool must not be tricked with fabricated `complete` metadata.

If the recovery manifest and source-attribution review make the 15 saved reports eligible,
a separate v1.1 study adapter may use the existing deterministic `extract_inventory` function
on those reports. It must verify the recovery manifest and source file hashes, retain the
preselected 15 targets and 45 persona assessments, keep Stage A blind, and preserve the
original one-human Stage A / optional AI / final-human adjudication order. The same original
sample was locked **before** these reports were generated; this compatibility amendment was
written **after** the interrupted run and must be disclosed as such. No scores or model
judgments enter claim selection. Report-level clustering and no numeric-score-accuracy claim
remain as in v1.0.

The current offline inventory contains 245 reviewable claims and 45 score-band packets, but
these are inventory counts, not verdicts or results. No initial/final human verdict, AI advice,
or adjudication is generated here. The v1.1 study cannot start its human workflow until its
separate adapter and source lock are implemented and checked; the original v1.0 study remains
closed to this incomplete run.
