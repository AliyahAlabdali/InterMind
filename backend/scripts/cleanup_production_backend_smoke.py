"""Erase only one marked synthetic backend smoke account and verify originals.

The operator supplies the restored Neon production owner password at a hidden
prompt. This helper never targets Azure, never reads candidate answers aloud,
and rolls back the deletion if the original backup's row fingerprints differ.
It is not a general account-deletion endpoint.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import re
import sys

import asyncpg
from production_encrypted_backup import BACKUP_DIR, HEAD, TABLES, catalog_snapshot, sha256
from production_neon_restore import DATABASE, HOST, NEW_HEAD, OWNER, tls_context

MARKER_PATTERN = re.compile(r"imsmoke-[0-9a-f]{12}\Z")


class Stop(RuntimeError):
    """Fixed non-sensitive failure label."""


def baseline() -> dict:
    manifests = list(BACKUP_DIR.glob(".env.production-dump-*.manifest.json"))
    if len(manifests) != 1:
        raise Stop("original private backup manifest inventory mismatch")
    path = manifests[0]
    archive = path.with_name(path.name.replace(".manifest.json", ".pgdump.age"))
    if not archive.is_file():
        raise Stop("original encrypted backup missing")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (data.get("source_database") != "intermind"
            or data.get("source_alembic") != HEAD
            or set(data.get("table_counts", {})) != TABLES
            or set(data.get("row_fingerprints_md5", {})) != TABLES
            or data.get("encrypted_archive_sha256") != sha256(archive)):
        raise Stop("original backup manifest or archive mismatch")
    return data


async def inspect_marker(conn: asyncpg.Connection, marker: str) -> tuple[str | None, list[str]]:
    email = marker + "@example.invalid"
    recruiter = await conn.fetchrow(
        "SELECT id FROM public.recruiters WHERE email=$1", email
    )
    recruiter_id = recruiter["id"] if recruiter else None
    jobs = await conn.fetch(
        "SELECT id, job_description FROM public.jobs WHERE recruiter_id=$1",
        recruiter_id,
    ) if recruiter_id else []
    if len(jobs) > 1 or any(
        not job["job_description"].startswith("InterMind isolated backend smoke " + marker)
        for job in jobs
    ):
        raise Stop("marker owns unexpected job records")
    job_ids = [job["id"] for job in jobs]
    candidate_rows = await conn.fetch(
        "SELECT id, name FROM public.candidates WHERE email=$1", email
    )
    if len(candidate_rows) > 1 or any(
        row["name"] != "Synthetic InterMind Candidate" for row in candidate_rows
    ):
        raise Stop("marker candidate inventory mismatch")
    for candidate in candidate_rows:
        linked = await conn.fetch(
            "SELECT job_id FROM public.interview_sessions WHERE candidate_id=$1",
            candidate["id"],
        )
        if any(row["job_id"] not in job_ids for row in linked):
            raise Stop("synthetic candidate is linked outside marker jobs")
    return recruiter_id, job_ids


async def verify_originals(conn: asyncpg.Connection, expected: dict) -> None:
    snapshot = await catalog_snapshot(conn, TABLES)
    for table in TABLES:
        if snapshot["table_counts"][table] != expected["table_counts"][table]:
            raise Stop("original table row count changed")
        if table not in {"alembic_version", "interview_sessions"} and (
            snapshot["row_fingerprints_md5"][table]
            != expected["row_fingerprints_md5"][table]
        ):
            raise Stop("original table row fingerprint changed")
    original_sessions = await conn.fetchval(
        "SELECT md5(coalesce(string_agg(h, '' ORDER BY h), '')) FROM "
        "(SELECT md5((to_jsonb(t) - 'last_activity_at')::text) AS h "
        "FROM public.interview_sessions AS t) AS row_hashes"
    )
    if original_sessions != expected["row_fingerprints_md5"]["interview_sessions"]:
        raise Stop("original interview content changed")


async def cleanup(markers: list[str], password: str, expected: dict) -> None:
    conn = await asyncpg.connect(
        host=HOST, port=5432, database=DATABASE, user=OWNER,
        password=password, ssl=tls_context(), command_timeout=40,
    )
    try:
        async with conn.transaction(readonly=True):
            identity = await conn.fetchrow(
                "SELECT current_database() AS db, session_user AS role, "
                "current_setting('server_version_num')::int AS version, "
                "current_setting('transaction_read_only') AS read_only"
            )
            if (identity["db"] != DATABASE or identity["role"] != OWNER
                    or not 180000 <= identity["version"] < 190000
                    or identity["read_only"] != "on"):
                raise Stop("direct Neon owner, database, version, or read-only mode mismatch")
            head = await conn.fetchval("SELECT version_num FROM public.alembic_version")
            if head != NEW_HEAD:
                raise Stop("Neon production Alembic head mismatch")
            inventories = [await inspect_marker(conn, marker) for marker in markers]
        print("PASS: exact Neon production target and marked synthetic ownership verified")
        if any(recruiter_id is None for recruiter_id, _ in inventories):
            raise Stop("a marked synthetic recruiter is absent; no deletion attempted")
        confirmation = f"DELETE {len(markers)} MARKED SMOKE ACCOUNTS"
        if input("Type " + confirmation + " to erase only marked smoke data: ") != confirmation:
            raise Stop("operator declined synthetic cleanup; no deletion attempted")
        async with conn.transaction():
            identity = await conn.fetchrow(
                "SELECT current_database() AS db, session_user AS role, "
                "current_setting('transaction_read_only') AS read_only"
            )
            if (
                identity["db"] != DATABASE
                or identity["role"] != OWNER
                or identity["read_only"] != "off"
            ):
                raise Stop("write transaction target mismatch")
            for marker, (recruiter_id, job_ids) in zip(markers, inventories, strict=True):
                checked_recruiter, checked_jobs = await inspect_marker(conn, marker)
                if checked_recruiter != recruiter_id or checked_jobs != job_ids:
                    raise Stop("marked synthetic inventory changed before deletion")
                for job_id in job_ids:
                    await conn.execute(
                        "DELETE FROM public.jobs WHERE id=$1 AND recruiter_id=$2",
                        job_id, recruiter_id,
                    )
                await conn.execute(
                    "DELETE FROM public.candidates WHERE email=$1 "
                    "AND name='Synthetic InterMind Candidate'",
                    marker + "@example.invalid",
                )
                await conn.execute(
                    "DELETE FROM public.recruiters WHERE id=$1 AND email=$2",
                    recruiter_id, marker + "@example.invalid",
                )
                if await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM public.recruiters WHERE email=$1)",
                    marker + "@example.invalid",
                ):
                    raise Stop("synthetic recruiter remained after deletion")
            await verify_originals(conn, expected)
        print("PASS: marked smoke data erased; all original counts and row fingerprints preserved")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marker", action="append", required=True)
    args = parser.parse_args()
    if len(set(args.marker)) != len(args.marker) or any(
        not MARKER_PATTERN.fullmatch(marker) for marker in args.marker
    ):
        raise Stop("synthetic marker format invalid; no connection attempted")
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise Stop("visible local terminal required for hidden credentials")
    expected = baseline()
    password = getpass.getpass("Neon production owner password (hidden): ")
    if not password:
        raise Stop("owner password absent; no connection attempted")
    asyncio.run(cleanup(args.marker, password, expected))


if __name__ == "__main__":
    try:
        main()
    except Stop as exc:
        print("STOP: " + str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        print("STOP: " + type(exc).__name__ + "; no automatic retry")
        raise SystemExit(1) from None
