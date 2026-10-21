# Recovered Claim & Score Validity v1.1: one-human review guide

This is a separate study of reports recovered from an **incomplete** v1.0 run. Its
compatibility method is the frozen `CLAIM_STUDY_v1.1.md`. The claim extraction,
rubric, sample, and sequence come from the unchanged frozen v1.0 Claim & Score
Validity study. The sample was locked before report generation; this v1.1 adapter
was prepared after the interrupted run. No v1.0 completed-run status is claimed.
The original deterministic sample remains three targets per report, one in each
category, across all five jobs and all three personas. The recovered extraction
produced 245 claim units at 245 report locations: no claim was lost or merged by
the frozen duplicate-collapsing rule, and the count matches the recovery manifest.

## Stage A, part 1: independent initial claim review

Open **only** `artifacts/20261011T223751Z/claim_validity_v1.1/claims_initial_blind.csv`
and the frozen `../claim_validity/RUBRIC_v1.md`. Do not open `inventory.json` or
`source.lock.json` during this stage. The internal inventory contains persona tiers,
model scores, and report IDs. The blind sheet contains 245 extracted claim units,
with the relevant job description, question, complete candidate answer, claim text,
and report location. A report-wide claim shows all ten question/answer pairs.
The displayed location is neutral: exact source paths, including whether a claim
was filed as a strength or weakness, remain in the source-locked internal inventory.
The sheet has no persona tier, model score, recommendation, automatic matching
verdict, or AI suggestion. Claim text itself is what you must assess.

Work in the sheet's existing row order. A practical cadence is five batches of 49
data rows: 1–49, 50–98, 99–147, 148–196, and 197–245 (the header is separate).
Save the **same** CSV after each batch. Do not sort, delete, or change context cells
or IDs. Only edit `verdict` and `note`. Reopen a saved batch to confirm multiline
answers and CSV quoting were preserved. Breaks between batches do not freeze or
release the score sheet.

Use exactly these verdicts, applying the full rubric:

- `SUPPORTED`: every substantive assertion follows from the answer and no
  material limitation is omitted.
- `PARTIALLY_SUPPORTED`: the central point is grounded, but an assertion is
  exaggerated or a material qualifier is missing.
- `UNSUPPORTED`: an invented or contradictory statement, or an unjustified
  strength or weakness.
- `UNCLEAR`: the provided answer context cannot settle the claim.

For any verdict except `SUPPORTED`, add a short `note` identifying the unsupported
part, omitted limitation, or uncertainty. Judge the entire claim unit. A list item
may contain more than one assertion; one unsupported component prevents a fully
supported verdict. The rubric includes the authoritative examples. Do not use
ChatGPT or Gemini before the initial human reviews are frozen.

From `backend/`, check progress offline with:

```powershell
../.venv/Scripts/python.exe -B -m evals.recovery_v11.claim_study verify
```

After **all 245** initial claim verdicts are your own and complete, freeze claims:

```powershell
../.venv/Scripts/python.exe -B -m evals.recovery_v11.claim_study freeze-claims
```

This validates IDs, unedited source context, allowed verdicts, and required notes;
locks the initial claim sheet by SHA-256; then releases the separate 45-row
`scores_initial.csv`. Do not open the score sheet before this step.

## Subsequent stages (do not start until claims are frozen)

Review score **bands**, not numerical score accuracy, in `scores_initial.csv`.
Use `DEFENSIBLE`, `NOT_DEFENSIBLE`, or `UNCLEAR` for `verdict`; use `YES`, `NO`, or
`UNCLEAR` for `material_omission`. Explain non-defensible/unclear bands and
yes/unclear omissions. Do not invent replacement ground-truth numeric scores.
Then run `freeze-initial` to lock both initial human sheets. This creates empty,
separate AI-suggestion files and blank final-adjudication files. Optional ChatGPT
and Gemini suggestions are AI assistance only, never independent human reviewers.
You remain the sole human adjudicator, record every final verdict, and explain
any changed verdict. Run `freeze-final` only when complete. The original initial
verdicts and optional AI suggestions remain separate and immutable after locking.

The study assesses claim validity and score-band defensibility, separate from the
recovered v1.1 quotation-fidelity result. Multiple claims can come from the same
answer or report. Final descriptive aggregation must account for report clustering;
245 claims are **not** 245 independent candidate samples. The five authored jobs,
three personas per job, incomplete source run, and missing per-request model
provenance remain limitations. No claim-validity result exists until human review.
