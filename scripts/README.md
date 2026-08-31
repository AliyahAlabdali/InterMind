# Scripts

Preprocessing / ETL scripts. These are run **manually** by a developer and are **never
imported by `app/`**.

Their job is to transform source data into the processed form the application knowledge
base will use in later milestones:

```
data/raw  --->  scripts/  --->  data/processed
```

No scripts exist yet - O*NET ingestion lands here in a later milestone.
