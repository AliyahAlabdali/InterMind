"""Stable identity for an assessment target - shared by plan-building and the runtime
interview graph so both sides agree on what "the same target" means without either importing
the other.

A target's id is a pure function of ``(job_id, category, normalized target name)`` - never a
fresh ``uuid4()`` - so the same target always resolves to the same id whether it was computed
once at plan-build time (see ``app.services.interview_planner``) or independently re-derived at
interview time (it isn't, currently - the graph trusts the id already on the plan's
``CoverageTarget``, exactly as it trusted a pre-generated ``InterviewQuestion.id`` before this
module existed - but the two must still be able to agree if anything ever needs to recompute
one, e.g. a future data migration).
"""

from __future__ import annotations

import hashlib

from app.domain.interview_plan import QuestionCategory
from app.services.text_normalize import normalize_name


def target_question_id(job_id: str, category: QuestionCategory | str, target: str) -> str:
    """Deterministic id for one ``(job_id, category, target)`` assessment target."""
    category_value = category.value if isinstance(category, QuestionCategory) else category
    key = f"{job_id}|{category_value}|{normalize_name(target)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
