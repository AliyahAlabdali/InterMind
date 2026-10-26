# Claim & Score Validity: retrospective methodological addendum v1.1a

**Status:** retrospective deviation and score-review release method. This document
does not amend the frozen Claim & Score Validity `PROTOCOL_v1.md`, `RUBRIC_v1.md`,
`SAMPLE_v1.json`, or the frozen recovery study `CLAIM_STUDY_v1.1.md`. It was written
after the claim adjudications. The source v1.0 evaluation run was incomplete;
the 15 persona reports were validated and reused only under the separate v1.1
recovery manifest. No completed v1.0 final-run status is implied.

## Actual claim-review sequence and deviation

The operator reports this sequence: 245 claims were extracted from the
source-locked recovered reports; AI-assisted claim review occurred; disagreements
were re-evaluated; one human reviewed and adopted the final 245 verdicts. The
score review had not been released at the time of this addendum. The supplied
`human_review/intermind_final_user_adjudicated_245.csv` is the original record of
those **human-adopted, AI-assisted final adjudications**. Its fields and source
context are validated before release, and its exact bytes are hashed in the
provenance manifest. The statement of sequence is operator supplied; the files
do not prove dates or reconstruct every review action.

The frozen protocol required an independent initial human claim review, a
SHA-256 lock of that initial sheet before AI assistance and score-sheet release,
separate AI suggestions, and later final human adjudication with changes from
initial verdicts explained. No documented independent pre-AI human claim sheet
or corresponding lock exists. The existing `claims_initial_blind.csv` is blank.
The adopted final file must **not** be copied into it, and the original
`freeze-claims`, `freeze-initial`, and `freeze-final` gates must not be invoked
using invented initial judgments. This addendum's provenance lock records the
adopted final file; it is not the missing initial-claim lock. The score sheet is
released through a separate, explicitly named v1.1a gate after validation.

Consequently, any later claim-validity summary may describe only the verdicts
of one human who adopted final judgments after AI assistance. It cannot claim
independent blind human claim labeling, inter-rater reliability, an
initial-to-final change rate, or unmodified compliance with the original staged
protocol. The claim sample itself was preselected before report generation, so
this deviation does not change targets or cherry-pick claims. The addendum was
written after the claim review and must be disclosed as retrospective. Claims
within a report are clustered, and the authored jobs and personas are not a
random sample of applicants. Missing per-request model provenance from the
incomplete source run remains a separate recovery limitation. No claim or
score-validity result is calculated by this release.

## Score-band defensibility release

The release uses exactly the 45 score assessment IDs from the source-locked
inventory: the original three preselected targets for each of the 15 reports.
It retains original report/assessment IDs, score values, qualitative bands,
job context, target, question, complete frozen candidate answer, and the
report's evidence, strengths, and weaknesses. These last three fields are the
recorded rationale, serialized without editing. The original v1.0 score-band
rubric governs the review. This is **not independent blind scoring**: the
reviewer sees InterMind's score, band, and rationale and decides whether the
band is defensible from the answer and its limitations. No human ground-truth
numeric score is requested or implied.

Only `DEFENSIBLE`, `NOT_DEFENSIBLE`, or `UNCLEAR` may go in `verdict`. Add a
`note` for `NOT_DEFENSIBLE` or `UNCLEAR`; a note for `DEFENSIBLE` is optional.
Use `YES`, `NO`, or `UNCLEAR` in `material_omission`, and explain `YES` or
`UNCLEAR` in `omission_detail`. These are the original protocol's fields and
rules. Read the full candidate answer, target question, job context, and
`RUBRIC_v1.md` before deciding. Do not treat the target or job description as
evidence the candidate demonstrated the capability. Do not change IDs,
context, model scores, bands, evidence, strengths, weaknesses, or row order.

The initial score-review sheet is released with all human judgment fields
blank. It is **not** frozen by release. The human review, any later score-review
lock, optional AI assistance, final human score adjudication, and descriptive
aggregation require separately approved work. Do not compare score verdicts
with InterMind judgments or publish a score-validity metric until that review
is completed and locked. No numeric score-accuracy claim follows from this
defensibility review.

## Reproducibility

`claim_score_addendum.py` verifies the frozen v1.0 and v1.1 source locks,
re-extracts the same 245 claims and 45 score packets, checks the adopted file
against claim IDs and exact source text/answers, checks every score ID against
the frozen preselected target rule, and refuses an existing release directory.
The release manifest records input paths, byte hashes, row counts, the
operator-supplied provenance statement, and the blank score template hash.
`RELEASE.lock.json` binds the manifest, addendum, tool, and released template.
Neither file substitutes for a missing independent initial-human claim lock.
