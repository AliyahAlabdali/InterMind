"""Read-only access to processed external knowledge bases (currently: O*NET).

Modules here only read finished artifacts under ``data/processed/``. They never read
``data/raw/`` and never run ETL - that happens in ``notebooks/`` (see
``notebooks/ONET_knowledge_base_pipeline.ipynb`` for O*NET).
"""
