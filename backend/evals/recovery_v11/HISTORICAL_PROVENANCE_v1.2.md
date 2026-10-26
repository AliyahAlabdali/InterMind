# Historical evaluation provenance verifier v1.2

This check authenticates the exact source bytes recorded by the frozen v1.1
protocol and recovery manifest. The historical evaluation gate calls it before
running its original data, label, score, and review checks. The frozen protocol,
lock, manifest, methodology, and saved results remain unchanged. A pass supports
the provenance of the incomplete historical run; it does **not** say that the
current serverless-ready runtime produced those results or that v1.0 became
complete.

The eleven application source files under `historical_source_v1_1/app/` are byte
snapshots. Nine still matched the lock or manifest in the current checkout at
recovery time.
The historical `interviews.py` came from Git blob
`dd4528dbd6426aed44df2cc25b3db4b284d91b7d` in `HEAD` at recovery time. The
historical `openai_client.py` came from local Git blob
`eaacb9f8986d4a193ac4f8eca3802cccfe44b3e6`, found in tree
`ef649d107b50bacfe0f062a86b2a9c48e832c79f`. Both Git blobs contain LF;
their original Windows checkout bytes contain CRLF and match the frozen SHA-256
values exactly. The snapshot files retain those CRLF bytes, and the local
`.gitattributes` disables checkout conversion for them. Verification hashes raw
bytes on every platform; it never normalizes content before comparison.

The original `audit.py` and `latency.py` were also copied byte for byte under
`historical_source_v1_1/evals/recovery_v11/` while they still matched their
frozen v1.1 SHA-256 values. Their active versions now route historical source
hashes to these snapshots, and the v1.2 verifier checks the snapshots against
the original lock. Protected datasets, labels, manifests, and results still
hash at their original locations, so tampering remains detectable.

Run from `backend/`:

```sh
python -c "from evals.recovery_v11.provenance_v12 import verify_historical_provenance; print(verify_historical_provenance())"
```

The verifier checks the original manifest digest, the locked protocol digest,
every v1.1 lock entry, and every manifest source-code digest. Current runtime
behavior must be tested separately with the application unit and integration
tests.

The gate's source-provenance check now tests the authenticated historical bytes.
It does not execute the historical application or substitute it for current
runtime tests. The current FastAPI, OpenAI, session, rate-limit, and interview
behavior is checked by independent application tests. Historical v1.1 results
must never be described as reproduced by the modified current runtime.

## Private results bundle and test commands

The 19 raw historical outputs in `backend/evals/results/` remain unchanged,
ignored, and private. Eight additional frozen review/label inputs with candidate
answers or context are also ignored. The historical outputs include scripted
candidate responses, report narratives, and evaluation traces. From `backend/`,
run the complete historical gate only after restoring the **entire** bundle:

```sh
python -m evals.private_history
```

This command first verifies the raw bytes of the original 19 results and eight
required review inputs against existing frozen locks, then runs the v1.2 source
and manifest verifier, and only then executes the historical evaluation tests.
A missing, extra, or altered result, or a missing or altered required review,
fails explicitly. It does not regenerate results or invoke OpenAI.
`python -m pytest -q` also remains the full test suite and requires the bundle.

For a public clean checkout, use the **explicit** runtime command below. The
`private_history` marker excludes only tests that require ignored historical
results, labels, or reviews; no historical assertion is converted into a skip
or a pass:

```sh
python -m pytest -q -m "not private_history"
```

Back up the ignored `backend/evals/` files as one private, access-controlled
tree. It must include all four dated `results/` directories, both `labels/*.csv`
files, both `recovery_v11/human_review/*.csv` files, and the four required
answer-bearing files under `recovery_v11/artifacts/20261011T223751Z/`:
`scores_band_review_v1.1a.csv`, `claims_initial_blind.csv`, `inventory.json`,
and `evidence_source_review_frozen.csv`. Other ignored blind review drafts and
backups are private but are not inputs to this historical gate; back them up
separately if they must be retained. Preserve original names and bytes,
including line endings. Back up the public lock files and verifier with the
repository revision. Restore the private tree under `backend/evals/`, then run
`python -m evals.private_history --check-only` before the complete gate. To
verify the private tree before restoring, use
`python -m evals.private_history --check-only --bundle-root <backup-evals-dir>`.
Keep the bundle and its verification output out of public build logs and Git.
The frozen protocol, acceptance criteria, datasets, labels, scores, and hashes
are not changed by this test selection.
