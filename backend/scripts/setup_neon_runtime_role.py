"""One-time, manually approved least-privilege role setup for Neon staging.

Never run this against the Azure database. ``--self-test`` has no network access;
``--apply`` requires hidden inputs and an explicit write confirmation. Credentials
exist only in process memory and are never printed or written to a file.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import ssl
import sys
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

import asyncpg

DATABASE = "intermind_staging"
OWNER = "intermind_staging_owner"
RUNTIME = "intermind_app_runtime"
HEAD = "a7d4b9e2c103"
TABLE_GRANTS = {
    "recruiters": "SELECT, INSERT",
    "recruiter_sessions": "SELECT, INSERT, DELETE",
    "rate_limit_events": "SELECT, INSERT, DELETE",
    "jobs": "SELECT, INSERT",
    "interview_plans": "SELECT, INSERT, UPDATE",
    "candidates": "SELECT, INSERT",
    "interview_sessions": "SELECT, INSERT, UPDATE",
    "interview_reports": "SELECT, INSERT, UPDATE",
    "activity_events": "SELECT, INSERT",
}


class InputValidationError(ValueError):
    """A fixed, non-sensitive label for a failure before any connection attempt."""


class ClientConfigurationError(ValueError):
    """A client-side connection failure before any database write."""


def direct_url(raw: str, expected_host: str) -> str:
    """Accept Neon's URL or quoted ``psql`` snippet; retain no TLS query options.

    The caller supplies the direct host copied separately from the Neon dashboard.
    Only the exact staging target is accepted. The returned URL stays in memory.
    """
    value = raw.strip()
    if value.lower().startswith("psql "):
        value = value[5:].strip()
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        value = value[1:-1]
    if any(char.isspace() or ord(char) < 32 for char in value):
        raise InputValidationError("connection snippet formatting")
    try:
        parts = urlsplit(value)
        port = parts.port or 5432
        username = unquote(parts.username or "")
        password = unquote(parts.password or "")
        database = unquote(parts.path.removeprefix("/"))
        query = parse_qs(parts.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise InputValidationError("connection snippet syntax") from None
    if parts.scheme not in {"postgres", "postgresql"}:
        raise InputValidationError("connection scheme")
    host = (parts.hostname or "").lower()
    expected = expected_host.strip().lower()
    if not expected.endswith(".neon.tech") or "-pooler" in expected:
        raise InputValidationError("expected direct host")
    if host != expected:
        raise InputValidationError("direct host match")
    if port != 5432:
        raise InputValidationError("direct port")
    if username != OWNER:
        raise InputValidationError("owner role")
    if database != DATABASE:
        raise InputValidationError("database name")
    if not password:
        raise InputValidationError("owner password presence")
    if parts.fragment:
        raise InputValidationError("connection snippet fragment")
    if set(query) - {"sslmode", "channel_binding"}:
        raise InputValidationError("connection snippet options")
    if "sslmode" in query and query["sslmode"] not in (["require"], ["verify-full"]):
        raise InputValidationError("TLS option")
    if "channel_binding" in query and query["channel_binding"] != ["require"]:
        raise InputValidationError("channel binding option")
    # asyncpg 0.31 accepts an SSLContext, not ssl="verify-full". Its explicit
    # context verifies both the certificate and the exact host. Remove snippet
    # options so they cannot override or conflict with that context.
    return urlunsplit(("postgresql", parts.netloc, parts.path, "", ""))


async def check_target(conn: asyncpg.Connection) -> None:
    async with conn.transaction(readonly=True):
        row = await conn.fetchrow(
            "SELECT current_database() AS db, session_user AS role, "
            "current_setting('transaction_read_only') AS read_only, "
            "current_setting('server_version_num')::int AS version"
        )
        if (
            row["db"] != DATABASE
            or row["role"] != OWNER
            or row["read_only"] != "on"
            or not (170000 <= row["version"] < 180000)
        ):
            raise RuntimeError("database identity or read-only preflight failed")
        revision = await conn.fetchval("SELECT version_num FROM public.alembic_version")
        if revision != HEAD:
            raise RuntimeError("Alembic revision does not match the staging head")
        existing = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)", RUNTIME
        )
        if existing:
            raise RuntimeError("runtime role already exists; inspect it before proceeding")
        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        actual = {row["tablename"] for row in tables}
        if actual != set(TABLE_GRANTS) | {"alembic_version"}:
            raise RuntimeError("staging table set differs from migrated schema")
        sequence = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_sequences "
            "WHERE schemaname = 'public' AND sequencename = 'rate_limit_events_id_seq')"
        )
        if not sequence:
            raise RuntimeError("rate-limit sequence is missing")


def grant_sql() -> tuple[str, ...]:
    return (
        f"GRANT CONNECT ON DATABASE {DATABASE} TO {RUNTIME}",
        f"GRANT USAGE ON SCHEMA public TO {RUNTIME}",
        *(
            f"GRANT {privileges} ON TABLE public.{table} TO {RUNTIME}"
            for table, privileges in TABLE_GRANTS.items()
        ),
        f"GRANT USAGE ON SEQUENCE public.rate_limit_events_id_seq TO {RUNTIME}",
    )


async def check_role(conn: asyncpg.Connection) -> None:
    role = await conn.fetchrow(
        "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, "
        "rolreplication, rolbypassrls, rolinherit FROM pg_roles WHERE rolname = $1",
        RUNTIME,
    )
    if role is None or dict(role) != {
        "rolcanlogin": True,
        "rolsuper": False,
        "rolcreatedb": False,
        "rolcreaterole": False,
        "rolreplication": False,
        "rolbypassrls": False,
        "rolinherit": False,
    }:
        raise RuntimeError("runtime role has unexpected attributes")
    membership = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_auth_members m "
        "JOIN pg_roles r ON r.oid = m.member WHERE r.rolname = $1)",
        RUNTIME,
    )
    if membership:
        raise RuntimeError("runtime role unexpectedly belongs to another role")
    forbidden = await conn.fetchrow(
        "SELECT has_database_privilege($1, $2, 'CREATE') AS database_create, "
        "has_schema_privilege($1, 'public', 'CREATE') AS schema_create, "
        "has_table_privilege($1, 'public.alembic_version', 'SELECT') AS alembic_read, "
        "has_table_privilege($1, 'public.alembic_version', 'INSERT') AS alembic_write",
        RUNTIME, DATABASE,
    )
    if any(forbidden.values()):
        raise RuntimeError("runtime role has CREATE or Alembic privileges")
    if not await conn.fetchval(
        "SELECT has_database_privilege($1, $2, 'CONNECT')", RUNTIME, DATABASE
    ) or not await conn.fetchval(
        "SELECT has_schema_privilege($1, 'public', 'USAGE')", RUNTIME
    ):
        raise RuntimeError("runtime connection or schema usage is missing")
    for table, privileges in TABLE_GRANTS.items():
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            actual = await conn.fetchval(
                "SELECT has_table_privilege($1, $2, $3)",
                RUNTIME, f"public.{table}", privilege,
            )
            if actual != (privilege in privileges.split(", ")):
                raise RuntimeError("runtime table privileges differ from application needs")
    for privilege in ("USAGE", "SELECT", "UPDATE"):
        actual = await conn.fetchval(
            "SELECT has_sequence_privilege($1, $2, $3)",
            RUNTIME, "public.rate_limit_events_id_seq", privilege,
        )
        if actual != (privilege == "USAGE"):
            raise RuntimeError("runtime sequence privileges differ from application needs")


async def apply() -> None:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise RuntimeError("a visible local terminal is required for hidden credential input")
    host = getpass.getpass("Exact DIRECT host from Neon dashboard (hidden): ")
    raw = getpass.getpass("Direct owner connection URL or psql snippet (hidden): ")
    password = getpass.getpass("New runtime password from your password manager (hidden): ")
    if len(password) < 32 or any(ord(char) < 32 for char in password):
        raise InputValidationError("runtime password policy (32 printable characters minimum)")
    url = direct_url(raw, host)
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise RuntimeError("verified TLS is unavailable")
    try:
        conn = await asyncpg.connect(dsn=url, ssl=context, timeout=15, command_timeout=15)
    except ValueError:
        # asyncpg may raise ValueError while interpreting a valid-looking URL.
        # The original exception might include connection details, so discard it.
        raise ClientConfigurationError("asyncpg connection configuration") from None
    try:
        await check_target(conn)
        print("PASS: direct staging target, verified TLS settings, schema, and head checked.")
        confirmation = input("Type CREATE intermind_app_runtime to authorize database writes: ")
        if confirmation != "CREATE intermind_app_runtime":
            print("STOP: no database write authorized.")
            return
        async with conn.transaction():
            # Recheck identity in the write transaction before the first write.
            identity = await conn.fetchrow(
                "SELECT current_database() AS db, session_user AS role, "
                "current_setting('transaction_read_only') AS read_only"
            )
            if (
                identity["db"] != DATABASE
                or identity["role"] != OWNER
                or identity["read_only"] != "off"
            ):
                raise RuntimeError("write transaction identity failed")
            quoted = await conn.fetchval("SELECT format('%L', $1::text)", password)
            await conn.execute(
                f"CREATE ROLE {RUNTIME} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB "
                f"NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {quoted}"
            )
            for sql in grant_sql():
                await conn.execute(sql)
            await check_role(conn)
        print("PASS: least-privilege runtime role created and verified.")
    finally:
        await conn.close()


async def status() -> None:
    """Read-only role-presence check for an interrupted setup attempt."""
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise RuntimeError("a visible local terminal is required for hidden credential input")
    host = getpass.getpass("Exact DIRECT host from Neon dashboard (hidden): ")
    raw = getpass.getpass("Direct owner connection URL or psql snippet (hidden): ")
    url = direct_url(raw, host)
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise RuntimeError("verified TLS is unavailable")
    conn = await asyncpg.connect(
        dsn=url, ssl=context, timeout=15, command_timeout=15,
        server_settings={"default_transaction_read_only": "on"},
    )
    try:
        async with conn.transaction(readonly=True):
            row = await conn.fetchrow(
                "SELECT current_database() AS db, session_user AS role, "
                "current_setting('transaction_read_only') AS read_only"
            )
            if (
                row["db"] != DATABASE
                or row["role"] != OWNER
                or row["read_only"] != "on"
            ):
                raise RuntimeError("read-only staging identity check failed")
            present = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)", RUNTIME
            )
            print("ROLE_STATUS: present" if present else "ROLE_STATUS: absent")
    finally:
        await conn.close()


def self_test() -> None:
    host = "ep-example.us-east-2.aws.neon.tech"
    base = "postgresql://intermind_staging_owner:synthetic%40password@" + host
    for snippet in (
        base + "/intermind_staging?sslmode=require&channel_binding=require",
        "psql '" + base + "/intermind_staging?sslmode=require'",
        'psql "' + base + '/intermind_staging?sslmode=verify-full"',
    ):
        assert direct_url(snippet, host).startswith("postgresql://")
    for bad in (
        base.replace(host, "ep-other.us-east-2.aws.neon.tech") + "/intermind_staging",
        base + "/postgres",
        base.replace("intermind_staging_owner", "intermind_runtime") + "/intermind_staging",
        base + "/intermind_staging?sslmode=disable",
        base + "/intermind_staging?application_name=unknown",
    ):
        try:
            direct_url(bad, host)
        except ValueError:
            continue
        raise AssertionError("an invalid staging connection snippet was accepted")
    assert "alembic_version" not in " ".join(grant_sql())
    print("PASS: synthetic URL and privilege-plan tests (no network).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true", help="synthetic tests; no network")
    group.add_argument("--apply", action="store_true", help="manual Neon database write")
    group.add_argument("--status", action="store_true", help="read-only Neon role-presence check")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        elif args.status:
            asyncio.run(status())
        else:
            asyncio.run(apply())
    except InputValidationError as exc:
        print(f"STOP: invalid {exc}. No database connection attempted.")
        raise SystemExit(1) from None
    except ClientConfigurationError as exc:
        print(f"STOP: {exc}. No database write attempted.")
        raise SystemExit(1) from None
    except (ValueError, RuntimeError, asyncpg.PostgresError, OSError) as exc:
        # Never print SQL or exception text: a driver error could contain a connection string.
        print(f"STOP: {type(exc).__name__}; no automatic retry. Check the target and role state.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
