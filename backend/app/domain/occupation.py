"""Domain models for O*NET occupation records and JobSpec-to-occupation matching.

These mirror the processed knowledge-base schema built by
``notebooks/ONET_knowledge_base_pipeline.ipynb`` (see ``data/processed/onet/onet_kb_meta.json``
for the authoritative field-by-field description). ``competencies`` is an InterMind signal
derived from O*NET's Skills file, not an O*NET-native "competency" - see that notebook,
Section 5.3, before treating these values as anything more than a proxy.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OccupationCompetency(BaseModel):
    """One O*NET Skill rated for this occupation (InterMind competency signal)."""

    skill: str
    importance: float
    level: float | None = None


class OccupationTechnology(BaseModel):
    """One O*NET Software Skills entry for this occupation."""

    technology: str
    category: str
    hot: bool = False
    in_demand: bool = False


class OccupationRecord(BaseModel):
    """One occupation from the processed O*NET knowledge base."""

    onet_soc_code: str
    title: str
    description: str
    competencies: list[OccupationCompetency] = Field(default_factory=list)
    technologies: list[OccupationTechnology] = Field(default_factory=list)
    core_tasks: list[str] = Field(default_factory=list)
    search_text: str = ""


class OccupationMatch(BaseModel):
    """One candidate occupation for a JobSpec, with its match score.

    The score comes from deterministic TF-IDF cosine similarity over ``search_text`` (see
    :mod:`app.knowledge.onet_kb`) - a retrieval baseline, not a validated classifier
    confidence. Do not present it to a user as an accuracy/probability figure.
    """

    onet_soc_code: str
    title: str
    score: float = Field(ge=0.0, description="TF-IDF cosine similarity, 0 (no overlap) to 1.")
