"""Guarded Azure PostgreSQL 18 backup to an age-encrypted archive.

No database write is performed. ``--preflight`` checks source identity, counts,
TLS, and pg_dump privileges without copying table data. ``--backup`` requires
the exact Azure App Service to be stopped before it streams a full dump directly
to age. No plaintext dump is written to disk or printed.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import ssl
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

import asyncpg
import certifi
import requests

logging.disable(logging.CRITICAL)

SUBSCRIPTION = "a28b5169-612e-41fb-9549-1bf540bbe43a"
GROUP = "intermind-rg"
SITE = "intermind-api"
SERVER = "intermind-db"
DATABASE = "intermind"
HEAD = "f3a821d9c604"
TABLES = {
    "activity_events", "alembic_version", "candidates", "interview_plans",
    "interview_reports", "interview_sessions", "jobs", "recruiters",
}
BASE = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}"
PG_BIN = Path(r"C:\Program Files\PostgreSQL\18\bin")
BACKUP_DIR = Path(r"C:\Users\Aliyah\Autonomous-AI-Interviewer")
SHARED_PRIVATE = BACKUP_DIR / ".env.production-migration-private"
AGE_BIN = (
    SHARED_PRIVATE if (SHARED_PRIVATE / "age.exe").is_file()
    else Path(r"C:\Users\Aliyah\AppData\Local\InterMind\Tools\age-v1.3.2")
)
IDENTITY = (
    SHARED_PRIVATE / "production-backup-identity.txt"
    if (SHARED_PRIVATE / "production-backup-identity.txt").is_file()
    else Path(r"C:\Users\Aliyah\AppData\Local\InterMind\Migration\production-backup-identity.txt")
)


class Stop(RuntimeError):
    """A fixed, non-sensitive failure message."""


def arm(method: str, path: str, token: str) -> dict:
    response = requests.request(
        method, BASE + path, headers={"Authorization": "Bearer " + token}, timeout=30
    )
    if response.status_code != 200:
        raise Stop(f"Azure metadata lookup HTTP {response.status_code}")
    return response.json()


def azure_source(
    *, require_stopped: bool, on_phase: Callable[[str], None] | None = None,
) -> tuple[str, str, str]:
    # Restore verification imports this module for archive/catalog helpers but
    # never needs the Azure SDK. Keep Azure auth local to source operations.
    if on_phase:
        on_phase("Azure SDK import")
    from azure.identity import InteractiveBrowserCredential

    with InteractiveBrowserCredential(
        tenant_id="AliyahAlabdali24gmail.onmicrosoft.com"
    ) as credential:
        if on_phase:
            on_phase("Azure interactive authentication")
        token = credential.get_token("https://management.azure.com/.default").token
        if on_phase:
            on_phase("Azure PostgreSQL metadata lookup")
        server = arm(
            "GET",
            f"/providers/Microsoft.DBforPostgreSQL/flexibleServers/{SERVER}"
            "?api-version=2024-08-01",
            token,
        )
        if on_phase:
            on_phase("Azure App Service metadata lookup")
        site = arm(
            "GET", f"/providers/Microsoft.Web/sites/{SITE}?api-version=2025-05-01", token
        )
        if on_phase:
            on_phase("Azure protected setting retrieval")
        settings = arm(
            "POST",
            f"/providers/Microsoft.Web/sites/{SITE}/config/appsettings/list"
            "?api-version=2025-05-01",
            token,
        )
    if on_phase:
        on_phase("Azure source target validation")
    host = server.get("properties", {}).get("fullyQualifiedDomainName", "").lower()
    if (server.get("name", "").lower() != SERVER
            or server.get("location", "").lower().replace(" ", "") != "uaenorth"
            or server.get("properties", {}).get("state") != "Ready"
            or server.get("properties", {}).get("version") != "18"
            or not host.endswith(".postgres.database.azure.com")):
        raise Stop("Azure PostgreSQL source identity or state mismatch")
    state = site.get("properties", {}).get("state", "")
    if (site.get("name", "").lower() != SITE
            or site.get("location", "").lower().replace(" ", "") != "uaenorth"
            or (require_stopped and state != "Stopped")
            or (not require_stopped and state != "Running")):
        raise Stop("Azure App Service identity or required state mismatch")
    raw = settings.get("properties", {}).get("DATABASE_URL", "")
    if not raw or raw.startswith("@Microsoft.KeyVault("):
        raise Stop("protected Azure database credential unavailable")
    parsed = urlsplit(raw.replace("postgresql+asyncpg://", "postgresql://", 1))
    if (parsed.scheme != "postgresql" or (parsed.hostname or "").lower() != host
            or (parsed.port or 5432) != 5432
            or unquote(parsed.path.removeprefix("/")) != DATABASE
            or not parsed.username or not parsed.password):
        raise Stop("protected Azure connection target mismatch")
    return host, unquote(parsed.username), unquote(parsed.password)


def pg_environment(password: str) -> dict[str, str]:
    trust_bundle = Path(certifi.where())
    if not trust_bundle.is_file():
        raise Stop("TLS certificate trust bundle missing")
    return {
        **os.environ,
        "PGPASSWORD": password,
        "PGSSLMODE": "verify-full",
        "PGSSLROOTCERT": str(trust_bundle),
        "PGCONNECT_TIMEOUT": "15",
    }


async def source_snapshot(host: str, user: str, password: str) -> dict:
    tls = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    if not tls.check_hostname or tls.verify_mode != ssl.CERT_REQUIRED:
        raise Stop("verified TLS context unavailable")
    conn = await asyncpg.connect(
        host=host, port=5432, database=DATABASE, user=user, password=password,
        ssl=tls, command_timeout=30,
        server_settings={"default_transaction_read_only": "on", "TimeZone": "UTC"},
    )
    try:
        async with conn.transaction(readonly=True):
            row = await conn.fetchrow(
                "SELECT current_database() AS db, session_user AS role, "
                "current_setting('server_version_num')::int AS version, "
                "current_setting('transaction_read_only') AS read_only"
            )
            if (row["db"] != DATABASE or row["role"] != user
                    or not 180000 <= row["version"] < 190000
                    or row["read_only"] != "on"):
                raise Stop("Azure source read-only identity mismatch")
            revision = await conn.fetchval("SELECT version_num FROM public.alembic_version")
            if revision != HEAD:
                raise Stop("Azure source Alembic revision mismatch")
            found = {
                record["tablename"] for record in await conn.fetch(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                )
            }
            if found != TABLES:
                raise Stop("Azure source table set mismatch")
            public_functions = await conn.fetchval(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n "
                "ON n.oid = p.pronamespace WHERE n.nspname = 'public'"
            )
            if public_functions:
                raise Stop("Azure source has unexpected public functions")
            return await catalog_snapshot(conn, TABLES)
    finally:
        await conn.close()


async def catalog_snapshot(conn: asyncpg.Connection, tables: set[str]) -> dict:
    """Compare counts, row multisets, and schema without returning record contents."""
    counts = {}
    fingerprints = {}
    for table in sorted(tables):
        if table not in TABLES | {"recruiter_sessions", "rate_limit_events"}:
            raise Stop("unexpected table name in catalog snapshot")
        counts[table] = await conn.fetchval(f'SELECT count(*) FROM public."{table}"')
        fingerprints[table] = await conn.fetchval(
            f'SELECT md5(coalesce(string_agg(h, \'\' ORDER BY h), \'\')) '
            f'FROM (SELECT md5(to_jsonb(t)::text) AS h '
            f'FROM public."{table}" AS t) AS row_hashes'
        )
    sequences = {
        row["sequencename"]: row["last_value"]
        for row in await conn.fetch(
            "SELECT sequencename, last_value FROM pg_sequences "
            "WHERE schemaname = 'public' ORDER BY sequencename"
        )
    }
    constraints = {
        f'{row["table_name"]}.{row["conname"]}': row["definition"]
        for row in await conn.fetch(
            "SELECT c.conrelid::regclass::text AS table_name, c.conname, "
            "pg_get_constraintdef(c.oid) AS definition FROM pg_constraint c "
            "JOIN pg_namespace n ON n.oid = c.connamespace "
            "WHERE n.nspname = 'public' ORDER BY c.conrelid, c.conname"
        )
    }
    indexes = {
        row["indexname"]: row["indexdef"]
        for row in await conn.fetch(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' ORDER BY indexname"
        )
    }
    return {
        "table_counts": counts,
        "row_fingerprints_md5": fingerprints,
        "sequences_last_value": sequences,
        "constraints": constraints,
        "indexes": indexes,
    }


def pg_dump_args(host: str, user: str, *, schema_only: bool) -> list[str]:
    args = [
        str(PG_BIN / "pg_dump.exe"), "--host", host, "--port", "5432",
        "--username", user, "--dbname", DATABASE, "--format=custom",
        "--no-owner", "--no-acl",
    ]
    if schema_only:
        args.append("--schema-only")
    return args


def executable_preflight() -> None:
    for path in (
        PG_BIN / "pg_dump.exe", PG_BIN / "pg_restore.exe",
        AGE_BIN / "age.exe", AGE_BIN / "age-keygen.exe", IDENTITY,
    ):
        if not path.is_file():
            raise Stop("backup executable or age identity missing")
    for path, prefix in (
        (PG_BIN / "pg_dump.exe", b"pg_dump (PostgreSQL) 18."),
        (PG_BIN / "pg_restore.exe", b"pg_restore (PostgreSQL) 18."),
        (AGE_BIN / "age.exe", b"v1.3.2"),
    ):
        result = subprocess.run(
            [str(path), "--version"], capture_output=True, timeout=15, check=False
        )
        if result.returncode or not result.stdout.strip().startswith(prefix):
            raise Stop("backup executable version mismatch")


def recipient() -> str:
    result = subprocess.run(
        [str(AGE_BIN / "age-keygen.exe"), "-y", str(IDENTITY)],
        capture_output=True, timeout=15, check=False,
    )
    value = result.stdout.decode("ascii", errors="ignore").strip()
    if result.returncode or not re.fullmatch(r"age1[023456789acdefghjklmnpqrstuvwxyz]+", value):
        raise Stop("backup identity recipient unavailable")
    return value


def schema_dump_check(host: str, user: str, password: str) -> None:
    result = subprocess.run(
        pg_dump_args(host, user, schema_only=True),
        env=pg_environment(password), stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, timeout=90, check=False,
    )
    if result.returncode or result.stderr:
        error = result.stderr.lower()
        category = next(
            (
                label for label, pattern in (
                    ("authentication", b"password authentication failed"),
                    ("certificate", b"certificate verify failed"),
                    ("ssl_configuration", b"sslrootcert"),
                    ("network", b"could not connect"),
                    ("permission", b"permission denied"),
                    ("server_version", b"server version mismatch"),
                    ("warning", b"warning"),
                ) if pattern in error
            ),
            "unclassified",
        )
        raise Stop(f"verified-TLS schema-only pg_dump failed or warned ({category})")
    print("PASS: schema-only pg_dump and verified TLS; no table data copied")


def encrypted_dump(host: str, user: str, password: str, destination: Path) -> None:
    encryption_recipient = recipient()
    dump = subprocess.Popen(
        pg_dump_args(host, user, schema_only=False),
        env=pg_environment(password), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert dump.stdout is not None
    assert dump.stderr is not None
    encrypt = None
    try:
        encrypt = subprocess.Popen(
            [str(AGE_BIN / "age.exe"), "-r", encryption_recipient, "-o", str(destination)],
            stdin=dump.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        dump.stdout.close()
        with ThreadPoolExecutor(max_workers=1) as readers:
            dump_error_future = readers.submit(dump.stderr.read)
            _, encryption_error = encrypt.communicate(timeout=180)
            dump.wait(timeout=180)
            dump_error = dump_error_future.result(timeout=5)
        if dump.returncode or encrypt.returncode or dump_error or encryption_error:
            raise Stop("pg_dump or age failed or warned; partial encrypted file retained")
    finally:
        if encrypt is not None and encrypt.poll() is None:
            encrypt.kill()
            encrypt.wait()
        if dump.poll() is None:
            dump.kill()
            dump.wait()


def verify_archive(destination: Path) -> None:
    if not destination.is_file() or destination.stat().st_size < 1000:
        raise Stop("encrypted archive absent or implausibly small")
    if destination.stat().st_size > 100_000_000:
        raise Stop("encrypted archive exceeds in-memory verification bound")
    decrypt = subprocess.run(
        [str(AGE_BIN / "age.exe"), "-d", "-i", str(IDENTITY), str(destination)],
        capture_output=True, timeout=180, check=False,
    )
    if decrypt.returncode or decrypt.stderr:
        raise Stop("full age authentication/decryption failed")
    if not decrypt.stdout.startswith(b"PGDMP"):
        raise Stop("decrypted backup is not a PostgreSQL custom archive")
    inspect = subprocess.run(
        [str(PG_BIN / "pg_restore.exe"), "--list"],
        input=decrypt.stdout, capture_output=True, timeout=60, check=False,
    )
    if inspect.returncode or inspect.stderr:
        raise Stop("pg_restore archive inspection failed")
    listing = inspect.stdout.decode("utf-8", errors="replace")
    if not all(f"TABLE public {table} " in listing for table in TABLES):
        raise Stop("pg_restore archive table inventory mismatch")
    print("PASS: full encrypted archive decrypts and pg_restore table inventory matches")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record_verified_archive(destination: Path, snapshot: dict, timestamp: str) -> None:
    manifest = BACKUP_DIR / f".env.production-dump-{timestamp}.manifest.json"
    if manifest.exists():
        raise Stop("private backup manifest already exists")
    verify_archive(destination)
    checksum = sha256(destination)
    manifest.write_text(
        json.dumps({
            "source_database": DATABASE,
            "source_pg_major": 18,
            "source_alembic": HEAD,
            **snapshot,
            "encrypted_archive_sha256": checksum,
            "encrypted_archive_bytes": destination.stat().st_size,
            "created_utc": timestamp,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    print("PASS: encrypted backup and private aggregate manifest verified")
    print("ARCHIVE_FILE=" + destination.name)
    print("ARCHIVE_SHA256=" + checksum)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight", action="store_true")
    group.add_argument("--backup", action="store_true")
    group.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()
    executable_preflight()
    host, user, password = azure_source(require_stopped=not args.preflight)
    print("PASS: exact Azure source and App Service state verified")
    snapshot = asyncio.run(source_snapshot(host, user, password))
    print("PASS: verified-TLS read-only source counts, row fingerprints, catalog, and Alembic head")
    for table, count in snapshot["table_counts"].items():
        print(f"SOURCE_COUNT {table}={count}")
    print("SOURCE_SEQUENCE_COUNT=" + str(len(snapshot["sequences_last_value"])))
    print("SOURCE_CONSTRAINT_COUNT=" + str(len(snapshot["constraints"])))
    print("SOURCE_INDEX_COUNT=" + str(len(snapshot["indexes"])))
    if args.preflight:
        schema_dump_check(host, user, password)
        return
    if args.verify_existing:
        archives = list(BACKUP_DIR.glob(".env.production-dump-*.pgdump.age"))
        if len(archives) != 1:
            raise Stop("exactly one incomplete encrypted backup is required")
        destination = archives[0]
        match = re.fullmatch(
            r"\.env\.production-dump-(\d{8}T\d{6}Z)\.pgdump\.age",
            destination.name,
        )
        if match is None:
            raise Stop("encrypted backup filename mismatch")
        record_verified_archive(destination, snapshot, match.group(1))
        return
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = BACKUP_DIR / f".env.production-dump-{timestamp}.pgdump.age"
    manifest = BACKUP_DIR / f".env.production-dump-{timestamp}.manifest.json"
    if destination.exists() or manifest.exists():
        raise Stop("backup destination already exists")
    encrypted_dump(host, user, password, destination)
    record_verified_archive(destination, snapshot, timestamp)


if __name__ == "__main__":
    try:
        main()
    except Stop as exc:
        print("STOP: " + str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        print("STOP: " + type(exc).__name__)
        raise SystemExit(1) from None
