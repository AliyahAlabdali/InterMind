# Data

Source datasets and the artifacts derived from them. Both `raw/` and `processed/` are
git-ignored, keeping only a `.gitkeep`, so large or licence-restricted files are never committed.
A fresh clone therefore has no knowledge base until it is built.

## Layout

| Directory | Contents |
|---|---|
| `raw/` | Untouched source downloads, exactly as obtained. Currently the O\*NET 31.0 text database under `raw/onet/db_31_0_text/`. Git-ignored. |
| `processed/` | Artifacts derived from `raw/`. Currently `processed/onet/`, holding `onet_kb.jsonl`, `occupation_index.csv` and `onet_kb_meta.json`. Git-ignored. |

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
