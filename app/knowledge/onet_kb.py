"""O*NET knowledge-base reader: load the Milestone 2 processed artifact and match a JobSpec
to occupations.

This module only reads ``onet_kb.jsonl`` under ``data/processed/onet/`` (built by
``notebooks/ONET_knowledge_base_pipeline.ipynb``). It never touches ``data/raw/`` and never
runs any ETL itself.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.core.exceptions import ConfigurationError, OccupationNotFound
from app.domain.job import JobSpec, Seniority
from app.domain.occupation import OccupationMatch, OccupationRecord

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KB_PATH = _REPO_ROOT / "data" / "processed" / "onet" / "onet_kb.jsonl"


def _load_records(path: Path) -> list[dict]:
    if not path.exists():
        raise ConfigurationError(
            f"O*NET knowledge base not found at {path}. Build it by running "
            "notebooks/ONET_knowledge_base_pipeline.ipynb end-to-end first."
        )
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ConfigurationError(f"{path}:{line_no}: invalid JSON ({exc})") from exc
    if not records:
        raise ConfigurationError(f"O*NET knowledge base at {path} is empty.")
    return records


def _jobspec_to_query_text(job_spec: JobSpec) -> str:
    """Mirror the search_text shape built in the notebook, so query and corpus share a format.

    Includes every JobSpec field that carries real matching signal - role title, seniority
    (when it's actually known), summary, skill names, competency names, and competency
    descriptions (when present) - so the matcher gets as much of the JobSpec as is meaningful.
    Fields that would only add boilerplate are skipped: an "unknown" seniority literal, or an
    empty "Skills:"/"Competencies:" label with nothing after it.
    """
    skill_names = " ".join(s.name for s in job_spec.skills)
    competency_names = " ".join(c.name for c in job_spec.competencies)
    competency_descriptions = " ".join(
        c.description for c in job_spec.competencies if c.description
    )
    parts = [
        job_spec.role_title,
        job_spec.seniority.value if job_spec.seniority != Seniority.UNKNOWN else "",
        job_spec.summary or "",
        f"Skills: {skill_names}." if skill_names else "",
        f"Competencies: {competency_names}." if competency_names else "",
        competency_descriptions,
    ]
    return " ".join(p for p in parts if p).strip()


class OnetKnowledgeBase:
    """Loads the processed O*NET KB once and serves occupation lookups + JobSpec matching.

    Matching is deterministic TF-IDF cosine similarity over each occupation's ``search_text``
    - the same proof-of-concept retrieval approach demonstrated in the Milestone 2 notebook,
    not a trained or validated classifier. ``min_df=1`` (vs. the notebook's ``min_df=2``,
    tuned for its 1000+ document corpus) keeps this usable with small KBs too, e.g. test
    fixtures.
    """

    def __init__(self, path: Path | str = DEFAULT_KB_PATH) -> None:
        self._path = Path(path)
        raw_records = _load_records(self._path)

        self._records: dict[str, OccupationRecord] = {}
        self._order: list[str] = []
        for line_no, rec in enumerate(raw_records, start=1):
            try:
                record = OccupationRecord.model_validate(rec)
            except ValidationError as exc:
                raise ConfigurationError(
                    f"{self._path}: record {line_no} is not a valid occupation record: {exc}"
                ) from exc
            if record.onet_soc_code in self._records:
                raise ConfigurationError(
                    f"{self._path}: duplicate onet_soc_code in knowledge base: "
                    f"{record.onet_soc_code!r} (record {line_no})"
                )
            self._records[record.onet_soc_code] = record
            self._order.append(record.onet_soc_code)

        self._vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
        self._matrix = self._vectorizer.fit_transform(
            self._records[code].search_text for code in self._order
        )

    def __len__(self) -> int:
        return len(self._order)

    def get_occupation(self, onet_soc_code: str) -> OccupationRecord:
        try:
            return self._records[onet_soc_code]
        except KeyError:
            raise OccupationNotFound(onet_soc_code) from None

    def match_jobspec(self, job_spec: JobSpec, top_k: int = 5) -> list[OccupationMatch]:
        """Return up to ``top_k`` candidate occupations, ranked by similarity, descending."""
        if top_k <= 0:
            raise ValueError(f"top_k must be a positive integer, got {top_k}")
        query = _jobspec_to_query_text(job_spec)
        sims = cosine_similarity(self._vectorizer.transform([query]), self._matrix)[0]
        ranked_idx = sims.argsort()[::-1][:top_k]
        return [
            OccupationMatch(
                onet_soc_code=self._order[i],
                title=self._records[self._order[i]].title,
                score=round(float(sims[i]), 4),
            )
            for i in ranked_idx
        ]
