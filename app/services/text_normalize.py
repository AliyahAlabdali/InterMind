"""Tiny shared text-normalization helper.

Used wherever two pieces of text - a selected signal's name and the target name an LLM (or
the fake client) echoes back for it - need to compare equal as "the same logical name"
regardless of case or whitespace differences. Kept as one function so
:mod:`app.services.interview_planner` and :mod:`app.services.question_generation` can never
drift apart on what "the same name" means.
"""

from __future__ import annotations

import re


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())
