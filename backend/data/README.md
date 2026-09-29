# Data

Source datasets and the artifacts derived from them. `raw/` and `processed/` are git-ignored down
to a `.gitkeep`, so large or restricted source files are never committed. The one exception is
`processed/onet/onet_kb.jsonl`, which is tracked (see below). A fresh clone therefore has the
knowledge base, but not the raw data or the other derived files.

## Layout

| Directory | Contents |
|---|---|
| `raw/` | Source downloads exactly as obtained, currently the O\*NET 31.0 text database under `raw/onet/db_31_0_text/`. |
| `processed/` | Artifacts derived from `raw/`. `processed/onet/` holds `onet_kb.jsonl`, `occupation_index.csv`, `onet_kb_meta.json` and a generated README saying to rerun the notebook rather than hand-edit them. Only `onet_kb.jsonl` is tracked, so the rest appears once the notebook has run. |

## Building and reading it

```
backend/data/raw/onet  --->  notebooks/ONET_knowledge_base_pipeline.ipynb  --->  backend/data/processed/onet
                                                                                              |
                                                                                              v
                                                                         backend/app/knowledge/onet_kb.py
```

`notebooks/ONET_knowledge_base_pipeline.ipynb` is run manually, end to end, and is the only thing
that writes to `processed/`. It sits at the repository root, outside `backend/`, and locates this
directory by searching upward for `backend/pyproject.toml`.

The application reads `processed/` directly. `backend/app/core/config.py` derives
`DEFAULT_ONET_KB_PATH` from the package location (`parents[2] / "data" / "processed" / "onet" /
"onet_kb.jsonl"`), so this directory has to stay a sibling of `backend/app/`; the `ONET_KB_PATH`
setting overrides it. `backend/app/knowledge/onet_kb.py` matches a job specification against
occupations using that file alone, never `raw/` and never the CSV index, which is there for
inspection. If the file is missing, interview planning fails with a message naming the notebook.

## Why `onet_kb.jsonl` is committed

Rebuilding it needs the hundreds of megabytes under `raw/onet/db_31_0_text/`, which are not in the
repository, so no deployment can regenerate it: a server would start healthy and then fail every
interview-plan request. Fetching it at runtime would add an Azure resource, a credential and a
startup failure mode for one file that changes about once a year. Tracking it costs 4.5 MB on disk
and about 0.7 MB compressed, and `.gitignore` un-ignores that exact path and nothing else under
`processed/`.

O\*NET is published by the U.S. Department of Labor and is redistributable with attribution, which
the root README carries. When O\*NET publishes a new version, rerun the notebook and commit the
new file.
