"""Compare live Azure records with the restored Neon copy without exposing rows.

Uses the protected App Service DATABASE_URL only in memory. The Neon direct owner
password is entered at a hidden local prompt. Both database connections use
certificate and hostname verification and repeatable-read, read-only transactions.
Only aggregate counts and difference counts are printed; no record or key is saved.
"""

from __future__ import annotations

import asyncio
import getpass
import hashlib
import ssl
import sys

import asyncpg
from production_encrypted_backup import DATABASE as AZURE_DATABASE
from production_encrypted_backup import HEAD as AZURE_HEAD
from production_encrypted_backup import TABLES, Stop, azure_source
from production_neon_restore import DATABASE as NEON_DATABASE
from production_neon_restore import HOST as NEON_HOST
from production_neon_restore import NEW_HEAD as NEON_HEAD
from production_neon_restore import OWNER as NEON_OWNER

KEYS = {
    "activity_events": "id",
    "candidates": "id",
    "interview_plans": "job_id",
    "interview_reports": "interview_id",
    "interview_sessions": "id",
    "jobs": "id",
    "recruiters": "id",
}
assert set(KEYS) == TABLES - {"alembic_version"}
CURRENT_PHASE = "local startup"


def phase(label: str) -> None:
    """Record a fixed, non-sensitive stage for a fail-closed diagnostic."""
    global CURRENT_PHASE
    CURRENT_PHASE = label


def safe_failure(exc: Exception) -> str:
    """Never format an exception message: it could contain connection details."""
    code = getattr(exc, "winerror", None) or getattr(exc, "errno", None)
    safe_code = str(code) if isinstance(code, int) else "unavailable"
    return (
        "phase=" + CURRENT_PHASE + "; type=" + type(exc).__name__
        + "; os_code=" + safe_code + "; no write attempted"
    )


def verified_tls() -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise Stop("verified TLS unavailable")
    return context


def aggregate_fingerprint(rows: dict[str, str]) -> str:
    """The old archive fingerprint algorithm, computed from in-memory row hashes."""
    return hashlib.md5("".join(sorted(rows.values())).encode("ascii")).hexdigest()


async def snapshot(
    *, host: str, database: str, user: str, password: str,
    expected_head: str, neon: bool,
) -> dict[str, dict[str, str]]:
    target = "Neon" if neon else "Azure"
    phase(target + " TLS context")
    tls = verified_tls()
    phase(target + " database TCP/TLS connection")
    conn = await asyncpg.connect(
        host=host, port=5432, database=database, user=user, password=password,
        ssl=tls, command_timeout=45,
        server_settings={"default_transaction_read_only": "on", "TimeZone": "UTC"},
    )
    try:
        phase(target + " read-only transaction and queries")
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            identity = await conn.fetchrow(
                "SELECT current_database() AS db, session_user AS role, "
                "current_setting('server_version_num')::int AS version, "
                "current_setting('transaction_read_only') AS read_only"
            )
            if (
                identity["db"] != database or identity["role"] != user
                or not 180000 <= identity["version"] < 190000
                or identity["read_only"] != "on"
            ):
                raise Stop("database identity, version, or read-only mode mismatch")
            head = await conn.fetchval("SELECT version_num FROM public.alembic_version")
            if head != expected_head:
                raise Stop("database Alembic revision mismatch")
            tables = {
                row["tablename"] for row in await conn.fetch(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                )
            }
            expected_tables = TABLES | (
                {"recruiter_sessions", "rate_limit_events"} if neon else set()
            )
            if tables != expected_tables:
                raise Stop("database public table inventory mismatch")
            result: dict[str, dict[str, str]] = {}
            for table, key in KEYS.items():
                # Both identifiers come from the fixed, reviewed whitelist above.
                content = (
                    "to_jsonb(t) - 'last_activity_at'"
                    if neon and table == "interview_sessions" else "to_jsonb(t)"
                )
                rows = await conn.fetch(
                    f'SELECT t."{key}"::text AS pk, md5(({content})::text) AS digest '
                    f'FROM public."{table}" AS t'
                )
                keyed = {row["pk"]: row["digest"] for row in rows}
                if len(keyed) != len(rows):
                    raise Stop("duplicate primary key in source inventory")
                result[table] = keyed
            return result
    finally:
        phase(target + " connection close")
        await conn.close()


def compare(
    azure: dict[str, dict[str, str]], neon: dict[str, dict[str, str]],
    baseline: dict,
) -> list[str]:
    lines = []
    for table in sorted(KEYS):
        old, new = azure[table], neon[table]
        azure_keys, neon_keys = set(old), set(new)
        changed = sum(old[key] != new[key] for key in azure_keys & neon_keys)
        azure_baseline = (
            len(old) == baseline["table_counts"][table]
            and aggregate_fingerprint(old) == baseline["row_fingerprints_md5"][table]
        )
        neon_baseline = (
            len(new) == baseline["table_counts"][table]
            and aggregate_fingerprint(new) == baseline["row_fingerprints_md5"][table]
        )
        lines.append(
            f"{table}: Azure={len(old)} Neon={len(new)} "
            f"Azure_only={len(azure_keys - neon_keys)} "
            f"Neon_only={len(neon_keys - azure_keys)} changed={changed} "
            f"Azure_matches_backup={azure_baseline} Neon_matches_backup={neon_baseline}"
        )
    return lines


async def run(azure_host: str, azure_user: str, azure_password: str,
              baseline: dict) -> None:
    azure = await snapshot(
        host=azure_host, database=AZURE_DATABASE, user=azure_user,
        password=azure_password, expected_head=AZURE_HEAD, neon=False,
    )
    print("PASS: Azure exact source, verified TLS, and read-only snapshot")
    phase("Neon hidden password input")
    neon_password = getpass.getpass("Neon production owner password (hidden): ")
    if not neon_password:
        raise Stop("Neon owner password absent; no Neon connection attempted")
    neon = await snapshot(
        host=NEON_HOST, database=NEON_DATABASE, user=NEON_OWNER,
        password=neon_password, expected_head=NEON_HEAD, neon=True,
    )
    print("PASS: Neon exact destination, verified TLS, and read-only snapshot")
    for line in compare(azure, neon, baseline):
        print(line)
    print("PASS: read-only comparison complete; no database writes attempted")


def main() -> None:
    phase("terminal availability check")
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise Stop("visible local terminal required for hidden credential input")
    from cleanup_production_backend_smoke import baseline as checked_baseline

    phase("local encrypted archive and manifest verification")
    baseline = checked_baseline()
    host, user, password = azure_source(require_stopped=False, on_phase=phase)
    phase("local asyncio startup")
    asyncio.run(run(host, user, password, baseline))


if __name__ == "__main__":
    try:
        main()
    except Stop as exc:
        print("STOP: " + str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        print("STOP: " + safe_failure(exc))
        raise SystemExit(1) from None
