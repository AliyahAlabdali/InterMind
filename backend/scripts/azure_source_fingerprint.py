"""Verify Azure's live source against one private backup fingerprint, read only.

Run inside the *main* ``intermind-api`` App Service container. The expected
digest is computed locally from the authenticated private backup manifest; it
is not a password or a database URL. This script never prints row data, row
hashes, or credentials, and never writes to the database or filesystem.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import re
import ssl
from pathlib import Path
from urllib.parse import unquote, urlsplit

import asyncpg

SITE = "intermind-api"
HOST = "intermind-db.postgres.database.azure.com"
DATABASE = "intermind"
HEAD = "f3a821d9c604"
TABLES = (
    "activity_events",
    "alembic_version",
    "candidates",
    "interview_plans",
    "interview_reports",
    "interview_sessions",
    "jobs",
    "recruiters",
)
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")


class Stop(RuntimeError):
    """A fixed, non-sensitive failure reason."""


def summary_digest(counts: dict[str, int], fingerprints: dict[str, str]) -> str:
    """Bind every expected table name, count, and archive-compatible row hash."""
    if set(counts) != set(TABLES) or set(fingerprints) != set(TABLES):
        raise Stop("table inventory mismatch")
    if any(not isinstance(counts[t], int) or counts[t] < 0 for t in TABLES):
        raise Stop("invalid row count")
    if any(re.fullmatch(r"[0-9a-f]{32}", fingerprints[t]) is None for t in TABLES):
        raise Stop("invalid row fingerprint")
    payload = "\n".join(f"{t}:{counts[t]}:{fingerprints[t]}" for t in TABLES)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def require_main_container(*, environ: dict[str, str], proc_root: Path = Path("/proc")) -> None:
    if environ.get("WEBSITE_SITE_NAME") != SITE or not environ.get("WEBSITE_INSTANCE_ID"):
        raise Stop("App Service identity mismatch")
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes()
            if b"uvicorn" in command and b"app.main:app" in command:
                root = Path(os.readlink(entry / "cwd"))
                if (root / "app/main.py").is_file():
                    return
        except OSError:
            continue
    raise Stop("running main application container not verified")


def source_target(raw: str) -> tuple[str, str]:
    if not raw or raw.startswith("@Microsoft.KeyVault("):
        raise Stop("protected Azure database setting unavailable")
    parsed = urlsplit(raw.replace("postgresql+asyncpg://", "postgresql://", 1))
    if (
        parsed.scheme != "postgresql"
        or parsed.hostname != HOST
        or (parsed.port or 5432) != 5432
        or unquote(parsed.path) != "/" + DATABASE
        or not parsed.username
        or not parsed.password
    ):
        raise Stop("Azure database target mismatch")
    return unquote(parsed.username), unquote(parsed.password)


async def verify(expected_digest: str, *, environ: dict[str, str] | None = None) -> None:
    if DIGEST_RE.fullmatch(expected_digest) is None:
        raise Stop("expected digest format invalid")
    environment = dict(os.environ) if environ is None else environ
    require_main_container(environ=environment)
    user, password = source_target(environment.get("DATABASE_URL", ""))
    tls = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    if not tls.check_hostname or tls.verify_mode != ssl.CERT_REQUIRED:
        raise Stop("verified TLS unavailable")
    conn = await asyncpg.connect(
        host=HOST,
        port=5432,
        database=DATABASE,
        user=user,
        password=password,
        ssl=tls,
        command_timeout=30,
        server_settings={"default_transaction_read_only": "on", "TimeZone": "UTC"},
    )
    try:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            identity = await conn.fetchrow(
                "SELECT current_database() AS db, session_user AS role, "
                "current_setting('server_version_num')::int AS version, "
                "current_setting('transaction_read_only') AS read_only"
            )
            if (
                identity["db"] != DATABASE
                or identity["role"] != user
                or not 180000 <= identity["version"] < 190000
                or identity["read_only"] != "on"
            ):
                raise Stop("database identity or read-only mode mismatch")
            if await conn.fetchval("SELECT version_num FROM public.alembic_version") != HEAD:
                raise Stop("Azure Alembic head mismatch")
            found = {
                row["tablename"]
                for row in await conn.fetch(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                )
            }
            if found != set(TABLES):
                raise Stop("Azure public table inventory mismatch")
            counts: dict[str, int] = {}
            fingerprints: dict[str, str] = {}
            for table in TABLES:
                # Identifiers come only from the fixed whitelist above.
                result = await conn.fetchrow(
                    f'SELECT count(*) AS n, md5(coalesce(string_agg(h, \'\' ORDER BY h), \'\')) '
                    f'AS fp FROM (SELECT md5(to_jsonb(t)::text) AS h '
                    f'FROM public."{table}" t) rows'
                )
                counts[table] = result["n"]
                fingerprints[table] = result["fp"]
            if summary_digest(counts, fingerprints) != expected_digest:
                raise Stop("Azure rows differ from authenticated backup manifest")
    finally:
        await conn.close()
    print("PASS: exact Azure main container, source, PG18, verified TLS, read-only snapshot")
    print("PASS: all eight original table counts and row fingerprints match the private backup")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    asyncio.run(verify(args.expected_sha256))


if __name__ == "__main__":
    try:
        main()
    except Stop as exc:
        print("STOP: " + str(exc) + "; no write attempted")
        raise SystemExit(1) from None
    except Exception as exc:
        # Driver errors can include connection strings. Print type only.
        print("STOP: sanitized " + type(exc).__name__ + "; no write attempted")
        raise SystemExit(1) from None
