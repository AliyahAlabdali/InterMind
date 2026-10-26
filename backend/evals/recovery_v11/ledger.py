"""Durable evaluation-only API attempt ledger; never records prompts or credentials."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

from app.llm.openai_client import OpenAIStructuredClient
from app.observability.trace import TraceRecorder

PRICING = {
    "version": "2026-10-12-gpt-4o-mini", "model": "gpt-4o-mini",
    "input_per_million_usd": 0.15, "cached_per_million_usd": 0.075,
    "output_per_million_usd": 0.60,
    "source": "https://developers.openai.com/api/docs/models/gpt-4o-mini",
}


class AttemptLedger:
    def __init__(self, path: Path, *, max_calls: int):
        self.path = path
        self.max_calls = max_calls
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS attempts (
            attempt_id TEXT PRIMARY KEY, endpoint_attempt INTEGER,
            schema_name TEXT NOT NULL,
            requested_model TEXT NOT NULL, returned_model TEXT,
            status TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER,
            cached_tokens INTEGER, pricing_version TEXT NOT NULL,
            estimated_usd REAL, error_type TEXT,
            started_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ended_utc TEXT)""")
        self.db.commit()

    def start(self, schema_name: str, requested_model: str,
              endpoint_attempt: int | None = None) -> str:
        with self.db:
            attempted = self.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            if attempted >= self.max_calls:
                raise RuntimeError("Evaluation API call cap reached")
            attempt_id = uuid4().hex
            self.db.execute(
                "INSERT INTO attempts "
                "(attempt_id,endpoint_attempt,schema_name,requested_model,status,pricing_version) "
                "VALUES (?,?,?,?,'unknown',?)",
                (attempt_id, endpoint_attempt, schema_name, requested_model,
                 PRICING["version"]),
            )
        return attempt_id

    def finish(self, attempt_id: str, *, returned_model: str | None = None,
               input_tokens: int | None = None, output_tokens: int | None = None,
               cached_tokens: int | None = None, error_type: str | None = None) -> None:
        if input_tokens is None or output_tokens is None:
            if any(value is not None for value in (input_tokens, output_tokens, cached_tokens)):
                raise ValueError("Partial usage is not accepted")
            cost = None
        else:
            cached = cached_tokens or 0
            if min(input_tokens, output_tokens, cached) < 0 or cached > input_tokens:
                raise ValueError("Invalid provider token usage")
            cost = ((input_tokens - cached) * PRICING["input_per_million_usd"]
                    + cached * PRICING["cached_per_million_usd"]
                    + output_tokens * PRICING["output_per_million_usd"]) / 1_000_000
        status = "failed" if error_type else "completed"
        with self.db:
            updated = self.db.execute(
                "UPDATE attempts SET returned_model=?,status=?,input_tokens=?,output_tokens=?,"
                "cached_tokens=?,estimated_usd=?,error_type=?,ended_utc=CURRENT_TIMESTAMP "
                "WHERE attempt_id=? AND status='unknown'",
                (returned_model, status, input_tokens, output_tokens, cached_tokens,
                 cost, error_type, attempt_id),
            ).rowcount
            if updated != 1:
                raise ValueError("Attempt missing or already reconciled")

    def summary(self) -> dict:
        rows = self.db.execute(
            "SELECT status,input_tokens,output_tokens,cached_tokens,estimated_usd "
            "FROM attempts"
        ).fetchall()
        return {
            "attempted": len(rows),
            "completed": sum(row[0] == "completed" for row in rows),
            "failed": sum(row[0] == "failed" for row in rows),
            "interrupted_or_unknown": sum(row[0] == "unknown" for row in rows),
            "input_tokens_known": sum(row[1] or 0 for row in rows),
            "output_tokens_known": sum(row[2] or 0 for row in rows),
            "cached_tokens_known": sum(row[3] or 0 for row in rows),
            "known_estimated_usd": sum(row[4] or 0 for row in rows),
            "total_cost_complete": all(row[4] is not None for row in rows),
        }

    def close(self) -> None:
        self.db.close()


class LedgerClient(OpenAIStructuredClient):
    """Uses the unchanged production client; persists each evaluation call around it."""

    def __init__(self, *, ledger: AttemptLedger, api_key: str, model: str):
        trace = TraceRecorder()
        super().__init__(api_key=api_key, model=model, trace=trace)
        self.ledger = ledger
        self.endpoint_attempt: int | None = None
        self._client = self._client.with_options(max_retries=0)
        self._original_parse = self._client.chat.completions.parse
        self._last_returned_model: str | None = None

        async def observed_parse(**kwargs):
            completion = await self._original_parse(**kwargs)
            self._last_returned_model = getattr(completion, "model", None)
            return completion

        # Evaluation-only interception observes the SDK response before the production
        # trace's fallback to the requested alias; request behavior is unchanged.
        self._client.chat.completions.parse = observed_parse

    async def generate_structured(self, *, prompt, input_text, schema):
        attempt_id = self.ledger.start(
            schema.__name__, self._model, self.endpoint_attempt
        )
        self._last_returned_model = None
        start = len(self._trace.events)
        error: Exception | None = None
        try:
            return await super().generate_structured(
                prompt=prompt, input_text=input_text, schema=schema
            )
        except Exception as exc:
            error = exc
            raise
        finally:
            # A hard termination leaves the committed start row as 'unknown'.
            completed = next((event for event in reversed(self._trace.events[start:])
                              if event.operation == "generate_structured_completed"), None)
            if completed is not None:
                detail = completed.details
                self.ledger.finish(
                    attempt_id, returned_model=self._last_returned_model,
                    input_tokens=detail.get("prompt_tokens"),
                    output_tokens=detail.get("completion_tokens"),
                    cached_tokens=detail.get("cached_prompt_tokens"),
                    error_type=type(error).__name__ if error else None,
                )
            elif error is not None:
                self.ledger.finish(attempt_id, error_type=type(error).__name__)
