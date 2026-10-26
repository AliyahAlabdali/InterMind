# Blind source review for recovered report evidence

The CSV beside the recovery manifest contains only the 22 evidence strings that the offline
source check could not establish by a unique exact match. It hides persona tier, report score,
and automatic classification. This review asks whether the string is faithful to candidate
words and where those words came from. It does **not** judge whether a report strength, weakness,
or numeric score is justified. The separate Claim & Score Validity study addresses that.

For each row, read the target question and answer, then all ten question/answer pairs. Fill
only `source_answer_index`, `verdict`, and `note`:

- `source_answer_index`: the numbered answer in `full_interview_context` that supports the
  evidence. Leave blank if no answer supports it. If several answers independently support it,
  list their numbers separated by semicolons and explain in `note`.
- `verdict`: `supported` when the candidate said or clearly implied the evidence string;
  `unsupported` when the string adds, changes, or reverses a material fact; `cannot_tell` when
  the complete answers do not settle it. `cannot_tell` is not counted as supported.
- `note`: explain every `unsupported` or `cannot_tell` decision and every multi-answer source.

Do not fill a verdict from the classification status or a model suggestion. Keep the original
CSV order and other columns unchanged. The 217 unique exact matches remain identifiable in
the locked manifest, but the missing per-turn history and cluster dependence must still be
disclosed in any later metric. No metric is calculated by this preparation step.
