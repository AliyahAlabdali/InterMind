# Claim & Score Validity v1.0: offline operator guide

This study is separate from the frozen v1.0 evaluation. It reads a **completed final** run; it never contacts OpenAI or changes a final result. Do not use the pilot directory. The frozen protocol, rubric, exact sample, code, and locks live here. The reviewed claim count is not known until actual final reports exist.

Run from `backend/` after the paid final run has been separately approved and completed:

```powershell
../.venv/Scripts/python.exe -B -m evals.claim_validity.study prepare evals/results/<FINAL_RUN> evals/claim_validity/reviews/<STUDY_RUN>
```

The tool creates `inventory.json` (internal join data), `source.lock.json`, and **only** `claims_initial_blind.csv`. Do not open `inventory.json` during blind claim review; it contains report IDs, persona tiers, and scores. The blind CSV contains an opaque claim ID, job context, question, full relevant candidate answer, report claim, and location. For report-wide claims, the answer cell contains all ten frozen Q/A pairs. Only fill `verdict` and `note`. Use exactly `SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNSUPPORTED`, or `UNCLEAR`; add a note for every verdict other than `SUPPORTED`. Do not edit context, IDs, or order. `RUBRIC_v1.md` gives examples. A list item or summary sentence may contain several assertions: judge the whole item and identify any unsupported part in the note.

When all claim rows are labeled, freeze them **before** opening scores:

```powershell
../.venv/Scripts/python.exe -B -m evals.claim_validity.study freeze-claims evals/claim_validity/reviews/<STUDY_RUN>
```

This verifies all claim IDs and context, writes `claims_initial.lock.json`, and releases `scores_initial.csv`. For each of the 45 target rows, read the full answer and reported strengths/weaknesses. Enter `DEFENSIBLE`, `NOT_DEFENSIBLE`, or `UNCLEAR` in `verdict`. Enter `YES`, `NO`, or `UNCLEAR` in `material_omission`; explain `YES` or `UNCLEAR` in `omission_detail`. Do not propose a replacement numeric score. Add a `note` for `NOT_DEFENSIBLE` or `UNCLEAR`.

Freeze both initial human sheets before any AI advice:

```powershell
../.venv/Scripts/python.exe -B -m evals.claim_validity.study freeze-initial evals/claim_validity/reviews/<STUDY_RUN>
```

This writes `initial.lock.json` and creates separate optional `claims_ai.csv` and `scores_ai.csv`, plus blank `claims_final.csv` and `scores_final.csv`. An AI file may remain header-only. If using ChatGPT or Gemini, add one row per `(ID, assistant)` with its suggestion and rationale. The suggestions are AI assistance, never independent human labels; do not send it your initial verdict if you want its view unanchored. Then you, the sole human reviewer, complete **every** final verdict. Set `ai_considered` to `YES` or `NO`; `YES` requires a recorded suggestion. Explain any change from the initial verdict or omission flag in `change_reason`. Initial CSVs must stay unchanged.

```powershell
../.venv/Scripts/python.exe -B -m evals.claim_validity.study freeze-final evals/claim_validity/reviews/<STUDY_RUN>
../.venv/Scripts/python.exe -B -m evals.claim_validity.study aggregate evals/claim_validity/reviews/<STUDY_RUN>
```

The first command validates completeness and locks final and AI sheets. The second verifies all hashes again and writes `metrics.json` once. An error never fills or changes a human verdict. A rerun needs a new study directory. Publish the four-way claim distribution and report-average fully supported rate beside, but never as, v1.0 quotation fidelity; label score-band defensibility separately. State one human reviewer, any AI assistance, all denominators, job-level range, and the limitations emitted in metrics.
