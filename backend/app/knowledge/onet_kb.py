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
from sklearn.preprocessing import normalize

from app.core.exceptions import ConfigurationError, OccupationNotFound
from app.domain.job import JobSpec, Seniority
from app.domain.occupation import OccupationMatch, OccupationRecord
from app.services.text_normalize import normalize_name as _normalize

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KB_PATH = _REPO_ROOT / "data" / "processed" / "onet" / "onet_kb.jsonl"

#: How much weight a query unigram keeps when it is also part of an active query bigram.
#:
#: The problem this solves, measured: a job description for a "Computer Vision Engineer"
#: matched **Orthoptists** - a clinical eye-care occupation - because the query encodes one
#: concept three times (``computer vision`` 0.5348 + ``vision`` 0.3723 + ``computer`` 0.1829).
#: No occupation record contains the adjacent phrase ``computer vision`` except Robotics
#: Engineers, so Orthoptists matched only the *fragments*, and ``vision`` alone - idf 5.03,
#: present in 43 of 1016 occupations, nearly all clinical - supplied 85% of the winning score.
#:
#: The redundancy is on the query side; the corpus side is legitimate (an occupation genuinely
#: about eyesight *should* score highly on ``vision``). So the fix is a query-side one: a
#: fragment of a phrase already represented in the query carries less independent information
#: than the phrase itself, and should not be counted again at full strength.
#:
#: 0.5 is not the best-scoring value on any dataset and was deliberately not tuned to one. It
#: reads as "a fragment carries at most half the evidence of the phrase containing it", and it
#: sits inside the stable region: the Orthoptists/Robotics crossover for the case above is at
#: f = 0.546, computed analytically from the two score decompositions, and the corrected
#: behaviour holds across f in [0.0, 0.6].
FRAGMENT_WEIGHT = 0.5


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


def _occupation_matching_text(record: OccupationRecord) -> str:
    """The text an occupation is matched *against*, rebuilt from its structured fields.

    Deliberately not ``record.search_text``. That field is the notebook's
    ``title + description + Skills + Technologies`` string, and it has two measured problems
    as a retrieval corpus:

    * **It omits ``core_tasks``.** The query side sends the JD's full responsibilities, so the
      richest part of a job description had nothing comparable to match against. Core tasks
      are present for 923 of 1016 occupations and roughly double the occupation-specific text.
    * **It includes O*NET's generic Skills, which carry no signal.** There are exactly ten
      distinct skill names in the whole corpus (Active Listening, Reading Comprehension,
      Critical Thinking, ...) and each appears in 89.6% of occupations - the same block
      repeated. They cannot discriminate between two occupations, and they dilute the terms
      that can.

    Technologies stay: 3671 distinct names at a 0.10% median prevalence make them the most
    occupation-specific evidence in the record (PyTorch and TensorFlow, for instance, are
    listed by two occupations and one respectively).

    Rebuilt at load time from fields the record already carries, so the tracked
    ``onet_kb.jsonl`` artifact is not regenerated and ``search_text`` keeps its documented
    meaning for any other consumer.
    """
    technologies = " ".join(t.technology for t in record.technologies)
    tasks = " ".join(record.core_tasks)
    parts = [
        record.title,
        record.description,
        f"Technologies: {technologies}." if technologies else "",
        tasks,
    ]
    return " ".join(p for p in parts if p).strip()


def _jobspec_to_query_text(job_spec: JobSpec) -> str:
    """Mirror the search_text shape built in the notebook, so query and corpus share a format.

    Includes every JobSpec field that carries real matching signal - role title, seniority
    (when it's actually known), summary, skill names, competency names, competency
    descriptions (when present), and responsibilities - so the matcher gets as much of the
    JobSpec as is meaningful. Fields that would only add boilerplate are skipped: an "unknown"
    seniority literal, or an empty "Skills:"/"Competencies:" label with nothing after it.
    """
    skill_names = " ".join(s.name for s in job_spec.skills)
    competency_names = " ".join(c.name for c in job_spec.competencies)
    competency_descriptions = " ".join(
        c.description for c in job_spec.competencies if c.description
    )
    responsibilities = " ".join(job_spec.responsibilities)
    parts = [
        job_spec.role_title,
        job_spec.seniority.value if job_spec.seniority != Seniority.UNKNOWN else "",
        job_spec.summary or "",
        f"Skills: {skill_names}." if skill_names else "",
        f"Competencies: {competency_names}." if competency_names else "",
        competency_descriptions,
        responsibilities,
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
            _occupation_matching_text(self._records[code]) for code in self._order
        )

        # For each bigram feature, which of its two words also exist as unigram features.
        # Built once here rather than per query: the vocabulary is fixed after fit, and this
        # turns fragment lookup into a dict hit instead of re-splitting 100k+ feature names on
        # every match. See `FRAGMENT_WEIGHT` and `_downweight_fragments`.
        vocabulary = self._vectorizer.vocabulary_
        self._bigram_fragments: dict[int, tuple[int, ...]] = {}
        for feature, column in vocabulary.items():
            if " " not in feature:
                continue
            parts = tuple(
                vocabulary[word] for word in feature.split() if word in vocabulary
            )
            if parts:
                self._bigram_fragments[column] = parts

        # How many distinct occupations list each technology name - see
        # `technology_prevalence`'s docstring for why this matters.
        self._technology_doc_freq: dict[str, int] = {}
        for code in self._order:
            names_in_this_occupation = {
                _normalize(t.technology) for t in self._records[code].technologies
            }
            for name in names_in_this_occupation:
                self._technology_doc_freq[name] = self._technology_doc_freq.get(name, 0) + 1

    def __len__(self) -> int:
        return len(self._order)

    def get_occupation(self, onet_soc_code: str) -> OccupationRecord:
        try:
            return self._records[onet_soc_code]
        except KeyError:
            raise OccupationNotFound(onet_soc_code) from None

    def _downweight_fragments(self, query_vector):
        """Reduce query unigrams that are already represented by an active query bigram.

        Query side only: the corpus matrix and the fitted vectorizer are untouched, so nothing
        here needs the KB to be rebuilt or ``onet_kb.jsonl`` to be regenerated.

        Each fragment is collected into a set *before* anything is scaled, then weighted
        exactly once. That matters: 19% of fragment unigrams belong to more than one active
        bigram (``develop`` appears in four for a single measured job description), and
        multiplying inside the loop would compound to ``FRAGMENT_WEIGHT`` squared or cubed for
        those - penalising a word for being productive rather than for being redundant.

        The vector is renormalised afterwards so scores stay on the same scale as before, which
        is what lets the absolute floor in ``InterviewPlannerService`` keep its meaning.
        """
        active = set(query_vector.indices)
        fragments = {
            unigram
            for column in query_vector.indices
            for unigram in self._bigram_fragments.get(column, ())
            if unigram in active
        }
        if not fragments:
            return query_vector

        adjusted = query_vector.copy()
        for position, column in enumerate(adjusted.indices):
            if column in fragments:
                adjusted.data[position] *= FRAGMENT_WEIGHT
        return normalize(adjusted)

    def _query_vector(self, job_spec: JobSpec):
        """The JobSpec's query text as a fragment-adjusted, unit-norm TF-IDF vector."""
        query = _jobspec_to_query_text(job_spec)
        return self._downweight_fragments(self._vectorizer.transform([query]))

    def match_jobspec(self, job_spec: JobSpec, top_k: int = 5) -> list[OccupationMatch]:
        """Return up to ``top_k`` candidate occupations, ranked by similarity, descending."""
        if top_k <= 0:
            raise ValueError(f"top_k must be a positive integer, got {top_k}")
        sims = cosine_similarity(self._query_vector(job_spec), self._matrix)[0]
        ranked_idx = sims.argsort()[::-1][:top_k]
        return [
            OccupationMatch(
                onet_soc_code=self._order[i],
                title=self._records[self._order[i]].title,
                score=round(float(sims[i]), 4),
            )
            for i in ranked_idx
        ]

    def technology_prevalence(self, technology_name: str) -> float:
        """Fraction of this KB's occupations whose technology list includes ``technology_name``.

        A cheap, general (no per-occupation or per-technology hard-coding) proxy for "how
        occupation-specific is this tool, really". Near-universal office software shows up in
        the technology list of most white-collar occupations regardless of domain - in the
        real O*NET 31.0 KB, Microsoft Excel/Word/Office sit at 60-83% - while genuinely
        occupation-specific tools sit far lower (e.g. Python ~12%, PostgreSQL <1%, a given EHR
        vendor product ~5%). See ``InterviewPlannerService``'s ubiquity filter, which uses this
        to stop a matched occupation's most generic, least-discriminating technologies from
        being presented as if they were specific signal about the job.
        """
        return self._technology_doc_freq.get(_normalize(technology_name), 0) / len(self._order)

    def relevance_to_jobspec(self, job_spec: JobSpec, text: str) -> float:
        """TF-IDF cosine similarity between ``text`` and the JobSpec's own query text.

        Reuses the exact vectorizer already fit for occupation matching (see ``match_jobspec``)
        rather than a new technique, so it inherits the same properties: shared *generic*
        vocabulary (e.g. "develop", "system") is naturally IDF-downweighted because it appears
        across most of the corpus, while shared *specific* vocabulary dominates the score. This
        is what lets an O*NET task sentence be checked for relevance against a specific JobSpec,
        instead of assuming every task belonging to a matched occupation applies to this job - a
        practical engineering heuristic, not a validated probability.

        Uses the same fragment-adjusted query representation as ``match_jobspec`` (see
        ``_downweight_fragments``), so a task is scored against the same reading of the job
        description that selected its occupation in the first place.
        """
        query_vector = self._query_vector(job_spec)
        text_vector = self._vectorizer.transform([text])
        return float(cosine_similarity(query_vector, text_vector)[0][0])
