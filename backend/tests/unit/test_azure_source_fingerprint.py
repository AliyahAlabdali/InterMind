"""Synthetic source-check tests: no Azure or PostgreSQL connection."""

from __future__ import annotations

import hashlib
import ssl
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import azure_source_fingerprint as source  # noqa: E402

EMPTY = hashlib.md5(b"").hexdigest()


def expected_snapshot() -> tuple[dict[str, int], dict[str, str]]:
    return ({table: 0 for table in source.TABLES}, {table: EMPTY for table in source.TABLES})


def test_summary_binds_every_table_count_and_row_fingerprint():
    counts, fingerprints = expected_snapshot()
    initial = source.summary_digest(counts, fingerprints)
    assert len(initial) == 64
    counts["recruiters"] = 1
    assert source.summary_digest(counts, fingerprints) != initial
    counts["recruiters"] = 0
    fingerprints["recruiters"] = "a" * 32
    assert source.summary_digest(counts, fingerprints) != initial
    del fingerprints["jobs"]
    with pytest.raises(source.Stop, match="table inventory"):
        source.summary_digest(counts, fingerprints)


def test_connection_target_requires_exact_azure_source_without_exposing_password():
    url = "postgresql+asyncpg://owner:synthetic%40password@intermind-db.postgres.database.azure.com/intermind"
    assert source.source_target(url) == ("owner", "synthetic@password")
    for changed in (
        url.replace("intermind-db", "other-db"),
        url.replace("/intermind", "/intermind_staging"),
        url.replace(":synthetic%40password", ":"),
        "@Microsoft.KeyVault(SecretUri=synthetic)",
    ):
        with pytest.raises(source.Stop) as error:
            source.source_target(changed)
        assert "synthetic@password" not in str(error.value)


def test_main_container_check_fails_closed_without_exact_site(monkeypatch, tmp_path):
    monkeypatch.setattr(source.os, "readlink", lambda _: str(tmp_path))
    with pytest.raises(source.Stop, match="App Service identity"):
        source.require_main_container(environ={}, proc_root=tmp_path)
    with pytest.raises(source.Stop, match="main application container"):
        source.require_main_container(
            environ={"WEBSITE_SITE_NAME": source.SITE, "WEBSITE_INSTANCE_ID": "synthetic"},
            proc_root=tmp_path,
        )


class SyntheticTransaction:
    def __init__(self, options):
        self.options = options

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class SyntheticConnection:
    def __init__(self, *, read_only: str = "on", changed: bool = False):
        self.read_only = read_only
        self.changed = changed
        self.queries: list[str] = []
        self.transaction_options = None
        self.closed = False

    def transaction(self, **options):
        self.transaction_options = options
        return SyntheticTransaction(options)

    async def fetchrow(self, sql):
        self.queries.append(sql)
        if "current_database()" in sql:
            return {
                "db": source.DATABASE,
                "role": "owner",
                "version": 180000,
                "read_only": self.read_only,
            }
        assert sql.startswith("SELECT count(*)")
        return {"n": 1 if self.changed and '"jobs"' in sql else 0, "fp": EMPTY}

    async def fetchval(self, sql):
        self.queries.append(sql)
        return source.HEAD

    async def fetch(self, sql):
        self.queries.append(sql)
        return [{"tablename": table} for table in source.TABLES]

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("read_only", "changed", "passes"),
    [("on", False, True), ("off", False, False), ("on", True, False)],
)
async def test_verified_tls_read_only_snapshot_and_mismatch_fail_closed(
    monkeypatch, capsys, read_only, changed, passes,
):
    conn = SyntheticConnection(read_only=read_only, changed=changed)
    calls = []

    async def connect(**options):
        calls.append(options)
        return conn

    monkeypatch.setattr(source, "require_main_container", lambda **_: None)
    monkeypatch.setattr(source.asyncpg, "connect", connect)
    counts, fingerprints = expected_snapshot()
    expected = source.summary_digest(counts, fingerprints)
    environ = {
        "DATABASE_URL": (
            "postgresql+asyncpg://owner:synthetic%40password"
            "@intermind-db.postgres.database.azure.com/intermind"
        )
    }
    if passes:
        await source.verify(expected, environ=environ)
        assert "PASS: all eight" in capsys.readouterr().out
    else:
        with pytest.raises(source.Stop):
            await source.verify(expected, environ=environ)
    assert len(calls) == 1
    assert calls[0]["host"] == source.HOST
    assert calls[0]["server_settings"]["default_transaction_read_only"] == "on"
    tls = calls[0]["ssl"]
    assert isinstance(tls, ssl.SSLContext)
    assert tls.verify_mode == ssl.CERT_REQUIRED and tls.check_hostname
    assert conn.transaction_options == {"isolation": "repeatable_read", "readonly": True}
    assert conn.closed
    assert all(query.lstrip().startswith("SELECT") for query in conn.queries)
