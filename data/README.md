# Data

All datasets (O*NET, competency frameworks, curated question banks, etc.) live here and
**only** here. Application code under `app/` never reads from this directory directly.

## Layout

| Directory            | Contents                                                                 |
|----------------------|-------------------------------------------------------------------------|
| `raw/`               | Untouched source downloads, exactly as obtained. Git-ignored.          |
| `processed/`         | Cleaned / normalised data derived from `raw/` by scripts. Git-ignored. |
| `questions/`         | Curated interview-question bank files (later milestones).              |
| `competencies/`      | Competency framework definitions (later milestones).                   |

## Flow

```
data/raw  --->  scripts/ (ETL, run manually)  --->  data/processed
```

`raw/` and `processed/` keep only a `.gitkeep`; their contents are git-ignored so large or
licence-restricted source files are never committed.
