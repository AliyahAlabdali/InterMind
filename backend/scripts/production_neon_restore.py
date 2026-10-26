"""Guarded one-time restore of the frozen Azure archive to empty Neon production.

Run only after the public maintenance page is live, Azure App Service is stopped,
and production_encrypted_backup.py --backup has passed. The owner password is
entered at a hidden local prompt and never written to a file or command line.
"""

from __future__ import annotations

import asyncio
import getpass
import json
import logging
import os
import re
import ssl
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

import asyncpg
from production_encrypted_backup import (
    AGE_BIN,
    BACKUP_DIR,
    HEAD,
    IDENTITY,
    PG_BIN,
    TABLES,
    Stop,
    catalog_snapshot,
    pg_environment,
    sha256,
    verify_archive,
)

logging.disable(logging.CRITICAL)

PROJECT = "jolly-hall-66091099"
HOST = "ep-twilight-grass-baaqucnp.c-8.eu-central-1.aws.neon.tech"
DATABASE = "intermind_production"
OWNER = "intermind_production_owner"
NEW_HEAD = "d91e5a7c2b40"
NEW_TABLES = TABLES | {"recruiter_sessions", "rate_limit_events"}


def archive_manifest() -> tuple[Path, dict]:
    manifests = list(BACKUP_DIR.glob(".env.production-dump-*.manifest.json"))
    if len(manifests) != 1:
        raise Stop("exactly one private production backup manifest is required")
    manifest_path = manifests[0]
    if not re.fullmatch(
        r"\.env\.production-dump-\d{8}T\d{6}Z\.manifest\.json",
        manifest_path.name,
    ):
        raise Stop("private backup manifest name mismatch")
    archive = manifest_path.with_name(
        manifest_path.name.replace(".manifest.json", ".pgdump.age")
    )
    if not archive.is_file():
        raise Stop("matching encrypted archive missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("source_database") != "intermind"
        or manifest.get("source_pg_major") != 18
        or manifest.get("source_alembic") != HEAD
        or set(manifest.get("table_counts", {})) != TABLES
        or set(manifest.get("row_fingerprints_md5", {})) != TABLES
        or not isinstance(manifest.get("constraints"), dict)
        or not isinstance(manifest.get("indexes"), dict)
        or not isinstance(manifest.get("sequences_last_value"), dict)
        or manifest.get("encrypted_archive_sha256") != sha256(archive)
        or manifest.get("encrypted_archive_bytes") != archive.stat().st_size
    ):
        raise Stop("private backup manifest or encrypted archive mismatch")
    verify_archive(archive)
    return archive, manifest


def tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise Stop("verified TLS context unavailable")
    return context


async def target_state(password: str, *, expected: str, manifest: dict | None = None) -> None:
    conn = await asyncpg.connect(
        host=HOST,
        port=5432,
        database=DATABASE,
        user=OWNER,
        password=password,
        ssl=tls_context(),
        command_timeout=90,
        server_settings={"default_transaction_read_only": "on", "TimeZone": "UTC"},
    )
    try:
        async with conn.transaction(readonly=True):
            row = await conn.fetchrow(
                "SELECT current_database() AS db, session_user AS role, "
                "current_setting('server_version_num')::int AS version, "
                "current_setting('transaction_read_only') AS read_only"
            )
            if (
                row["db"] != DATABASE
                or row["role"] != OWNER
                or not 180000 <= row["version"] < 190000
                or row["read_only"] != "on"
            ):
                raise Stop("Neon direct destination identity or read-only mode mismatch")
            tables = {
                item["tablename"]
                for item in await conn.fetch(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                )
            }
            functions = await conn.fetchval(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n "
                "ON n.oid = p.pronamespace WHERE n.nspname = 'public'"
            )
            if expected == "empty":
                relations = await conn.fetchval(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid = c.relnamespace WHERE n.nspname = 'public' "
                    "AND c.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')"
                )
                if tables or relations or functions:
                    raise Stop("Neon destination is no longer empty")
                return
            if expected == "restored":
                if tables != TABLES or functions:
                    raise Stop("restored table/function inventory mismatch")
                revision = await conn.fetchval(
                    "SELECT version_num FROM public.alembic_version"
                )
                if revision != HEAD:
                    raise Stop("restored Alembic revision mismatch")
                snapshot = await catalog_snapshot(conn, TABLES)
                if any(snapshot[key] != manifest[key] for key in snapshot):
                    raise Stop("restored counts, records, sequence, or schema mismatch")
                return
            if expected != "migrated" or tables != NEW_TABLES or functions:
                raise Stop("migrated schema inventory mismatch")
            revision = await conn.fetchval("SELECT version_num FROM public.alembic_version")
            if revision != NEW_HEAD:
                raise Stop("post-migration Alembic head mismatch")
            snapshot = await catalog_snapshot(conn, NEW_TABLES)
            for table in TABLES - {"alembic_version"}:
                if snapshot["table_counts"][table] != manifest["table_counts"][table]:
                    raise Stop("post-migration source table count changed")
                if table != "interview_sessions" and (
                    snapshot["row_fingerprints_md5"][table]
                    != manifest["row_fingerprints_md5"][table]
                ):
                    raise Stop("post-migration original records changed")
            original_sessions = await conn.fetchval(
                "SELECT md5(coalesce(string_agg(h, '' ORDER BY h), '')) FROM "
                "(SELECT md5((to_jsonb(t) - 'last_activity_at')::text) AS h "
                "FROM public.interview_sessions AS t) AS row_hashes"
            )
            if original_sessions != manifest["row_fingerprints_md5"]["interview_sessions"]:
                raise Stop("post-migration interview content changed")
            if snapshot["table_counts"]["recruiter_sessions"] != 0 or (
                snapshot["table_counts"]["rate_limit_events"] != 0
            ):
                raise Stop("new serverless tables unexpectedly contain rows")
            if "rate_limit_events_id_seq" not in snapshot["sequences_last_value"]:
                raise Stop("new rate-limit sequence missing")
            if any(
                snapshot["constraints"].get(name) != definition
                for name, definition in manifest["constraints"].items()
            ) or any(
                snapshot["indexes"].get(name) != definition
                for name, definition in manifest["indexes"].items()
            ):
                raise Stop("original schema constraints or indexes missing")
            null_activity = await conn.fetchval(
                "SELECT count(*) FROM public.interview_sessions "
                "WHERE last_activity_at IS NULL"
            )
            if null_activity:
                raise Stop("interview retention clock backfill incomplete")
    finally:
        await conn.close()


def restore_archive(archive: Path, password: str) -> None:
    env = pg_environment(password)
    decrypt = subprocess.Popen(
        [str(AGE_BIN / "age.exe"), "-d", "-i", str(IDENTITY), str(archive)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert decrypt.stdout is not None
    assert decrypt.stderr is not None
    restore = None
    try:
        restore = subprocess.Popen(
            [
                str(PG_BIN / "pg_restore.exe"), "--host", HOST, "--port", "5432",
                "--username", OWNER, "--dbname", DATABASE, "--single-transaction",
                "--exit-on-error", "--no-owner", "--no-acl",
            ],
            stdin=decrypt.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=env,
        )
        decrypt.stdout.close()
        with ThreadPoolExecutor(max_workers=1) as readers:
            decrypt_error_future = readers.submit(decrypt.stderr.read)
            _, restore_error = restore.communicate(timeout=300)
            decrypt.wait(timeout=300)
            decrypt_error = decrypt_error_future.result(timeout=5)
        if restore.returncode or decrypt.returncode or restore_error or decrypt_error:
            raise Stop("Neon pg_restore failed or warned; keep maintenance active")
    finally:
        if restore is not None and restore.poll() is None:
            restore.kill()
            restore.wait()
        if decrypt.poll() is None:
            decrypt.kill()
            decrypt.wait()


def migration_chain() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    if scripts.get_current_head() != NEW_HEAD or (
        scripts.get_revision(NEW_HEAD).down_revision != "a7d4b9e2c103"
    ) or scripts.get_revision("a7d4b9e2c103").down_revision != HEAD:
        raise Stop("local Alembic migration chain differs from approved revisions")


def migrate(password: str) -> None:
    migration_chain()
    backend = Path(__file__).resolve().parents[1]
    python = backend.parent / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        raise Stop("local migration Python environment missing")
    url = (
        f"postgresql+asyncpg://{OWNER}:{quote(password, safe='')}@{HOST}/{DATABASE}"
    )
    env = {
        **os.environ,
        "DATABASE_URL": url,
        "DATABASE_SSL_VERIFY_FULL": "true",
        "REQUIRE_DATABASE": "true",
        "DATABASE_POOL_MODE": "null",
    }
    result = subprocess.run(
        [str(python), "-B", "-m", "alembic", "upgrade", "head"],
        cwd=backend,
        env=env,
        capture_output=True,
        timeout=180,
        check=False,
    )
    if result.returncode:
        raise Stop("reviewed Alembic migration failed; keep maintenance active")


def main() -> None:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise Stop("visible local terminal required for hidden owner password")
    archive, manifest = archive_manifest()
    migration_chain()
    password = getpass.getpass("Neon production owner password (hidden): ")
    if not password:
        raise Stop("owner password missing")
    asyncio.run(target_state(password, expected="empty"))
    print("PASS: exact empty Neon direct target, PG18, owner, verified TLS")
    restore_archive(archive, password)
    print("PASS: encrypted archive restored transactionally")
    asyncio.run(target_state(password, expected="restored", manifest=manifest))
    print("PASS: all source records, counts, sequences, constraints, indexes, and old head match")
    migrate(password)
    asyncio.run(target_state(password, expected="migrated", manifest=manifest))
    print("PASS: approved Alembic chain, all original records, and final schema verified")


if __name__ == "__main__":
    try:
        main()
    except Stop as exc:
        print("STOP: " + str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        print("STOP: " + type(exc).__name__ + "; keep maintenance active")
        raise SystemExit(1) from None
