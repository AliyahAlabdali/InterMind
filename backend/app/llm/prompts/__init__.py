"""Versioned prompt loading.

Prompts are product logic. They live as ``<name>_<version>.md`` files in this package so
each one is reviewable, diffable, and pinned by the caller.
"""

from __future__ import annotations

from pathlib import Path

_PROMPT_DIR = Path(__file__).parent


def load_prompt(name: str, version: str) -> str:
    """Return the text of ``<name>_<version>.md`` from this package.

    Raises:
        FileNotFoundError: no such prompt file.
    """
    path = _PROMPT_DIR / f"{name}_{version}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt not found: {path.name}")
    return path.read_text(encoding="utf-8").strip()
