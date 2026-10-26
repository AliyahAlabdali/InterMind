"""Synthetic guards for isolated production smoke and secret repair tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import cleanup_production_backend_smoke as cleanup  # noqa: E402
import repair_isolated_openai_key as repair  # noqa: E402


@pytest.mark.asyncio
async def test_cleanup_requires_marker_owned_job_and_candidate():
    marker = "imsmoke-0123456789ab"

    class FakeConnection:
        async def fetchrow(self, _sql, _email):
            return {"id": "synthetic-recruiter"}

        async def fetch(self, sql, _value):
            if "FROM public.jobs" in sql:
                return [{"id": "synthetic-job", "job_description": (
                    "InterMind isolated backend smoke " + marker + ". Python API engineer."
                )}]
            if "FROM public.candidates" in sql:
                return [{"id": "synthetic-candidate", "name": "Synthetic InterMind Candidate"}]
            if "FROM public.interview_sessions" in sql:
                return [{"job_id": "synthetic-job"}]
            raise AssertionError("unexpected read")

    assert await cleanup.inspect_marker(FakeConnection(), marker) == (
        "synthetic-recruiter", ["synthetic-job"]
    )


@pytest.mark.asyncio
async def test_cleanup_rejects_unmarked_job_before_deletion():
    class FakeConnection:
        async def fetchrow(self, _sql, _email):
            return {"id": "synthetic-recruiter"}

        async def fetch(self, sql, _value):
            if "FROM public.jobs" in sql:
                return [{"id": "other", "job_description": "Unmarked job"}]
            raise AssertionError("candidate lookup must not follow a failed job guard")

    with pytest.raises(cleanup.Stop, match="unexpected job records"):
        await cleanup.inspect_marker(FakeConnection(), "imsmoke-0123456789ab")


@pytest.mark.asyncio
async def test_original_fingerprint_mismatch_aborts_cleanup(monkeypatch):
    expected = {
        "table_counts": {table: 1 for table in cleanup.TABLES},
        "row_fingerprints_md5": {table: "original" for table in cleanup.TABLES},
    }

    async def changed_snapshot(_conn, _tables):
        return {
            "table_counts": {table: 1 for table in cleanup.TABLES},
            "row_fingerprints_md5": {
                table: ("changed" if table == "jobs" else "original")
                for table in cleanup.TABLES
            },
        }

    monkeypatch.setattr(cleanup, "catalog_snapshot", changed_snapshot)
    with pytest.raises(cleanup.Stop, match="row fingerprint changed"):
        await cleanup.verify_originals(object(), expected)


def test_manual_openai_key_check_targets_only_exact_isolated_project(monkeypatch, capsys):
    key = "synthetic-secret-key-for-test"
    monkeypatch.setattr(repair.sys, "argv", ["repair_isolated_openai_key.py", "--set"])
    monkeypatch.setattr(repair.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(repair.sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr(repair.getpass, "getpass", lambda _prompt: key)
    monkeypatch.setattr(
        repair.requests,
        "get",
        lambda url, headers, timeout: SimpleNamespace(
            status_code=200, json=lambda: {"id": "gpt-4o-mini"}
        ),
    )
    project = {
        "id": repair.VERCEL_PROJECT,
        "rootDirectory": "backend",
        "owner": {"slug": repair.VERCEL_SCOPE},
    }
    monkeypatch.setattr(
        repair.subprocess,
        "run",
        lambda args, **_kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(project)),
    )
    monkeypatch.setattr(repair, "vercel_cli", lambda: "vercel.cmd")
    changes = []
    monkeypatch.setattr(
        repair,
        "vercel_add",
        lambda name, value, **options: changes.append((name, value, options)),
    )
    repair.main()
    assert changes == [("OPENAI_API_KEY", key, {"secret": True, "force": True})]
    assert key not in capsys.readouterr().out
