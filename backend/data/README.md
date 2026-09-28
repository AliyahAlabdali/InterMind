# Data

Source datasets and the artifacts derived from them. Both `raw/` and `processed/` are
git-ignored, keeping only a `.gitkeep`, so large or licence-restricted files are never committed.
There is **one deliberate exception**: `processed/onet/onet_kb.jsonl` is tracked, because it is
the only file the running application reads and a deployment has no way to rebuild it (see below).
A fresh clone therefore has the knowledge base, but not the raw data or the other derived files.

## Layout

| Directory | Contents |
|---|---|
| `raw/` | Untouched source downloads, exactly as obtained. Currently the O\*NET 31.0 text database under `raw/onet/db_31_0_text/`. Git-ignored. |
| `processed/` | Artifacts derived from `raw/`. Currently `processed/onet/`, holding `onet_kb.jsonl`, `occupation_index.csv`, `onet_kb_meta.json` and a generated `README.md`. Git-ignored **except `onet_kb.jsonl`**, so everything else here appears only after the notebook runs. |

## How it is built and read

```
backend/data/raw/onet  --->  notebooks/ONET_knowledge_base_pipeline.ipynb  --->  backend/data/processed/onet
                                                                                              |
                                                                                              v
                                                                         backend/app/knowledge/onet_kb.py
```

The pipeline is a notebook, run manually end to end. The notebook lives at the repository root,
outside `backend/`, and resolves this directory by searching upward for `backend/pyproject.toml`.
It is the only thing that writes to `processed/`, and it also generates a
`processed/onet/README.md` alongside the artifacts saying not to hand-edit them. That generated
README is git-ignored like the rest of `processed/onet/`, so it appears only after you run the
notebook; a fresh clone will not have it.

**The application reads `processed/` directly.** `backend/app/core/config.py` defines
`DEFAULT_ONET_KB_PATH` relative to the package location, as `parents[2] / "data" / "processed" /
"onet" / "onet_kb.jsonl"`. That is why this directory has to stay a sibling of `backend/app/`.
The `ONET_KB_PATH` setting overrides it. `backend/app/knowledge/onet_kb.py` loads that file to
match a job specification against occupations, and reads nothing else here: never `raw/`, and
never the CSV index, which exists for inspection rather than for the application.

If the file is missing, interview planning fails with a message naming the notebook to run.

## Why `onet_kb.jsonl` is committed

Rebuilding it needs `raw/onet/db_31_0_text/`, which is hundreds of megabytes and is not in the
repository, so no deployment can regenerate it. A server would start healthy and then fail every
interview-plan request. Fetching it at runtime from blob storage would add an Azure resource, a
credential and a new startup failure mode for one file that changes about once a year.

Tracking it is the only deterministic option, and it is cheap: 4.5 MB on disk, about 0.7 MB
compressed in git. `.gitignore` un-ignores that exact path and nothing else under `processed/`;
the CSV index and meta JSON are inspection aids and stay out.

O\*NET is published by the U.S. Department of Labor and is redistributable with attribution, which
the repository README carries. Re-run the notebook and commit the new file when O\*NET releases a
new version.
