# Data

Source datasets and the artifacts derived from them. Both `raw/` and `processed/` are
git-ignored, keeping only a `.gitkeep`, so large or licence-restricted files are never committed —
**with one deliberate exception**: `processed/onet/onet_kb.jsonl` is tracked, because it is the
only file the running application reads and a deployment has no way to rebuild it (see below).
A fresh clone therefore has the knowledge base, but not the raw data or the other derived files.

## Layout

| Directory | Contents |
|---|---|
| `raw/` | Untouched source downloads, exactly as obtained. Currently the O\*NET 31.0 text database under `raw/onet/db_31_0_text/`. Git-ignored. |
| `processed/` | Artifacts derived from `raw/`. Currently `processed/onet/`, holding `onet_kb.jsonl`, `occupation_index.csv` and `onet_kb_meta.json`. Git-ignored **except `onet_kb.jsonl`**. |

## How it is built and read

```
data/raw/onet  --->  notebooks/ONET_knowledge_base_pipeline.ipynb  --->  data/processed/onet
                                                                              |
                                                                              v
                                                             app/knowledge/onet_kb.py
```

The pipeline is a notebook, run manually end to end. It is the only thing that writes to
`processed/`, which is why `data/processed/onet/README.md` says not to hand-edit those files.

**The application reads `data/processed/` directly.** `app/core/config.py` defines
`DEFAULT_ONET_KB_PATH` as `data/processed/onet/onet_kb.jsonl`, overridable with the
`ONET_KB_PATH` setting, and `app/knowledge/onet_kb.py` loads that file to match a job
specification against occupations. It reads nothing else here: never `raw/`, and never the CSV
index, which exists for inspection rather than for the application.

If the file is missing, interview planning fails with a message naming the notebook to run.

## Why `onet_kb.jsonl` is committed

Rebuilding it needs `raw/onet/db_31_0_text/`, which is hundreds of megabytes and is not in the
repository, so no deployment can regenerate it — a server would start healthy and then fail every
interview-plan request. Fetching it at runtime from blob storage would add an Azure resource, a
credential and a new startup failure mode for one file that changes about once a year.

Tracking it is the only deterministic option, and it is cheap: ~4.7 MB on disk, ~0.7 MB compressed
in git. `.gitignore` un-ignores that exact path and nothing else under `processed/`; the CSV index
and meta JSON are inspection aids and stay out.

O\*NET is published by the U.S. Department of Labor and is redistributable with attribution, which
the repository README carries. Re-run the notebook and commit the new file when O\*NET releases a
new version.
