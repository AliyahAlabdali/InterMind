# One-human claim and score review rubric v1.0

Read the **full candidate answer** and question before judging a report item. The job description tells you what was asked; it is not evidence of what the candidate did. Treat an answer's explicit limitation as seriously as its positive detail. Record only your own initial judgment in Stage A. AI advice belongs in a different file after the initial lock.

## Claim verdicts

| Verdict | Use when |
| --- | --- |
| `SUPPORTED` | Every substantive assertion is stated or necessarily implied by the answer, and no omitted qualifier materially changes its meaning. A fair observation that the answer lacks detail may be supported. |
| `PARTIALLY_SUPPORTED` | The central action or fact is supported, but the report exaggerates it, misses a material limitation, or makes a compound claim with only some supported parts. |
| `UNSUPPORTED` | The candidate did not say it; attribution, cause, quantity, or outcome is invented; the answer contradicts it; or a strength/weakness makes an inference the answer cannot justify. |
| `UNCLEAR` | The available answer genuinely cannot settle the assertion. Use sparingly and explain the ambiguity. |

Examples (rubric illustrations, **not** study results):

- Answer: “I wrote a cleanup script, but did not schedule or monitor it.” Claim: “Wrote a cleanup script.” → `SUPPORTED`. Claim: “Delivered a reliable production automation.” → `PARTIALLY_SUPPORTED` or `UNSUPPORTED` depending on its wording; record the omitted deployment limit.
- Answer: “I fixed a join but did not validate source counts.” Claim: “Reconciled the corrected results to the source.” → `UNSUPPORTED`.
- Answer: “Another engineer found the token issue.” Claim: “The candidate diagnosed the token issue.” → `UNSUPPORTED` (invented attribution).
- Answer: “I added webhook retries but did not test duplicate delivery.” Claim: “Added retries.” → `SUPPORTED`; claim: “Made webhook delivery reliable.” → `PARTIALLY_SUPPORTED` because an important failure mode was not checked.
- A vague answer does not establish that the candidate *lacks* a skill. “No example was provided” may be supported; “the candidate stated they lack experience” is unsupported unless they said so.

For compound items, evaluate every asserted part. Record the missing or contradictory portion in `note`. Do not upgrade an item simply because its evidence quote appears verbatim; quotation fidelity is a different test. Check unsupported strengths and unsupported weaknesses equally. On the separate target score sheet, mark whether a material limitation relevant to the target's claims or score was omitted, and quote or paraphrase the omitted part in `omission_detail`.

## Score-band review

After initial claim verdicts are locked, read the score sheet. `DEFENSIBLE` means the existing band is a reasonable interpretation of the answer, even if you would choose a different exact decimal or an adjacent band. `NOT_DEFENSIBLE` means a material contradiction, absence of demonstrated work, or ignored limitation makes that band untenable; explain why. `UNCLEAR` means the answer does not permit a confident call. This is **not** an invitation to write a preferred numeric score.

The bands are the application's existing categories: insufficient `<0.35`, limited `0.35–<0.60`, moderate `0.60–<0.80`, strong `>=0.80`. Assess the candidate's evidence for the asked target, not general competence or hiring suitability. The offline tool checks overall-score arithmetic separately; a correct calculation does not make its input target judgments valid.

Stage C belongs to the same human. Keep the initial CSV unchanged, put any ChatGPT/Gemini suggestions in the AI file, and enter final verdicts and reasons for changes in the final CSV. Never present AI suggestions as a second human rating.
