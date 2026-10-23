"""One-time, guarded Neon staging retention migration.

Run manually from backend/ with --apply. The direct host and owner password are
entered at hidden prompts, kept in process memory, and never printed or saved.
--self-test checks only synthetic inputs and does not use the network.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import hashlib
import os
import re
import ssl
import sys
from pathlib import Path
from urllib.parse import quote

import asyncpg
from alembic.config import Config

from alembic import command

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DATABASE = "intermind_staging"
OWNER = "intermind_staging_owner"
RUNTIME = "intermind_app_runtime"
OLD_HEAD = "a7d4b9e2c103"
NEW_HEAD = "d91e5a7c2b40"
DELETE_TABLES = (
    "activity_events", "interview_reports", "interview_sessions", "candidates"
)
# Authenticated earlier against the Neon staging pooled endpoint. A direct endpoint
# must produce exactly this digest after adding -pooler to its first DNS label.
STAGING_POOLER_HOST_SHA256 = (
    "4ae47810ef982f0600d99d20e205671f61dfeffecfe2852b57071eb94d99d92e"
)


class HostValidationError(ValueError):
    """A fixed, credential-free reason for rejecting a direct host."""


def validate_direct_host(host: str, *, expected_digest: str = STAGING_POOLER_HOST_SHA256) -> str:
    host = host.strip().lower()
    # Neon's Frankfurt hostname includes the cell label before the AWS region,
    # e.g. ep-example.c-8.eu-central-1.aws.neon.tech.
    if not re.fullmatch(r"ep-[a-z0-9-]+\.c-[0-9]+\.eu-central-1\.aws\.neon\.tech", host):
        raise HostValidationError("direct host format")
    if "-pooler" in host:
        raise HostValidationError("pooled host supplied")
    first, rest = host.split(".", 1)
    pooled = f"{first}-pooler.{rest}"
    digest = hashlib.sha256(pooled.encode("ascii")).hexdigest()
    if digest != expected_digest:
        raise HostValidationError("direct host fingerprint mismatch")
    return host


def tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise RuntimeError("TLS verification is not enabled")
    return context


async def inspect(host: str, password: str, *, expected_head: str) -> None:
    connection = await asyncpg.connect(
        host=host,
        port=5432,
        user=OWNER,
        password=password,
        database=DATABASE,
        ssl=tls_context(),
        server_settings={"default_transaction_read_only": "on"},
        timeout=15,
    )
    try:
        async with connection.transaction(readonly=True):
            identity = await connection.fetchrow(
                "SELECT current_database() AS db, session_user AS role, "
                "current_setting('server_version_num')::int AS version, "
                "current_setting('transaction_read_only') AS read_only"
            )
            if (
                identity["db"] != DATABASE
                or identity["role"] != OWNER
                or identity["read_only"] != "on"
                or not 170000 <= identity["version"] < 180000
            ):
                raise RuntimeError("staging identity, version, or read-only check failed")
            revision = await connection.fetchval(
                "SELECT version_num FROM public.alembic_version"
            )
            if revision != expected_head:
                raise RuntimeError("Alembic head differs from expected")
            column_exists = await connection.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='interview_sessions' "
                "AND column_name='last_activity_at')"
            )
            if column_exists != (expected_head == NEW_HEAD):
                raise RuntimeError("retention column does not match Alembic head")
            runtime = await connection.fetchrow(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
                "FROM pg_roles WHERE rolname=$1", RUNTIME
            )
            if runtime is None or any(
                runtime[key] for key in ("rolsuper", "rolcreatedb", "rolcreaterole", "rolbypassrls")
            ):
                raise RuntimeError("runtime role missing or elevated")
            if expected_head == NEW_HEAD:
                for table in DELETE_TABLES:
                    allowed = await connection.fetchval(
                        "SELECT has_table_privilege($1, $2, 'DELETE')",
                        RUNTIME, f"public.{table}",
                    )
                    if not allowed:
                        raise RuntimeError("runtime delete privilege missing")
    finally:
        await connection.close()


def self_test() -> None:
    example = "ep-synthetic.c-8.eu-central-1.aws.neon.tech"
    pooled = "ep-synthetic-pooler.c-8.eu-central-1.aws.neon.tech"
    digest = hashlib.sha256(pooled.encode("ascii")).hexdigest()
    assert validate_direct_host(example, expected_digest=digest) == example
    for bad in (
        "ep-other.c-8.eu-central-1.aws.neon.tech",
        pooled,
        "ep-synthetic.c-8.eu-central-1.aws.neon.tech.evil.invalid",
        "ep-synthetic.c-8.eu-central-1.aws.neon.tech/other",
        "ep-synthetic.eu-central-1.aws.neon.tech",
    ):
        try:
            validate_direct_host(bad, expected_digest=digest)
        except HostValidationError:
            continue
        raise AssertionError("invalid host accepted")
    tls_context()
    assert "alembic_version" not in DELETE_TABLES
    print("PASS: synthetic host and TLS checks; no network used.")


async def grant_runtime_deletes(host: str, password: str) -> None:
    connection = await asyncpg.connect(
        host=host, port=5432, user=OWNER, password=password, database=DATABASE,
        ssl=tls_context(), timeout=15,
    )
    try:
        async with connection.transaction():
            identity = await connection.fetchrow(
                "SELECT current_database() AS db, session_user AS role, "
                "(SELECT version_num FROM public.alembic_version) AS revision"
            )
            if (
                identity["db"] != DATABASE or identity["role"] != OWNER
                or identity["revision"] != NEW_HEAD
            ):
                raise RuntimeError("grant target differs from migrated staging database")
            # The owner already created these tables. Grant only what the new
            # erasure and purge paths need; no schema CREATE or version-table access.
            await connection.execute(
                "GRANT DELETE ON TABLE public.activity_events, public.interview_reports, "
                "public.interview_sessions, public.candidates TO intermind_app_runtime"
            )
    finally:
        await connection.close()


def apply() -> None:
    host = validate_direct_host(getpass.getpass("Exact DIRECT staging host (hidden): "))
    password = getpass.getpass("Staging owner password (hidden): ")
    if not password:
        raise ValueError("missing owner password")
    asyncio.run(inspect(host, password, expected_head=OLD_HEAD))
    print("PASS: exact staging target, verified TLS, read-only head and schema preflight.")
    prompt = "Type MIGRATE AND GRANT intermind_staging to apply revision and grants: "
    if input(prompt).strip() != (
        "MIGRATE AND GRANT intermind_staging"
    ):
        print("STOP: migration not confirmed; no write attempted.")
        return
    url = (
        f"postgresql+asyncpg://{OWNER}:{quote(password, safe='')}"
        f"@{host}/{DATABASE}"
    )
    old_url = os.environ.get("DATABASE_URL")
    old_tls = os.environ.get("DATABASE_SSL_VERIFY_FULL")
    try:
        os.environ["DATABASE_URL"] = url
        os.environ["DATABASE_SSL_VERIFY_FULL"] = "true"
        print("Applying only retention revision d91e5a7c2b40 to staging.")
        command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), NEW_HEAD)
    finally:
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url
        if old_tls is None:
            os.environ.pop("DATABASE_SSL_VERIFY_FULL", None)
        else:
            os.environ["DATABASE_SSL_VERIFY_FULL"] = old_tls
    asyncio.run(grant_runtime_deletes(host, password))
    asyncio.run(inspect(host, password, expected_head=NEW_HEAD))
    print("PASS: staging retention migration, narrow runtime grants, and head verified.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            apply()
    except HostValidationError as error:
        print(f"STOP: {error}; no database connection attempted.")
        raise SystemExit(1) from None
    except Exception as error:  # noqa: BLE001 - never expose driver exception text
        # Never print driver exception details: they can include a URL or password.
        print(f"STOP: {type(error).__name__}; no automatic retry. Inspect target state.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
