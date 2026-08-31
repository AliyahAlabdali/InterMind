"""Append-only trace of LLM interactions.

Deliberately minimal for Milestone 1: an in-memory list plus a log line. The call sites
and this interface are what matter; a later milestone can swap in a persistent recorder
without touching them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("llm.trace")


@dataclass(frozen=True)
class TraceEvent:
    operation: str
    timestamp: str
    details: dict[str, Any]


@dataclass
class TraceRecorder:
    events: list[TraceEvent] = field(default_factory=list)

    def record(self, *, operation: str, **details: Any) -> None:
        event = TraceEvent(
            operation=operation,
            timestamp=datetime.now(UTC).isoformat(),
            details=details,
        )
        self.events.append(event)
        logger.info("%s %s", operation, details)
