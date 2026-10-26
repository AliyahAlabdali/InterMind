"""Create and verify the least-privilege Neon production runtime role once.

Run only after production_neon_restore.py passes. The owner and new runtime
passwords are entered at hidden local prompts. ``--role-only`` avoids relying
on Vercel CLI login in the operator's PowerShell; it performs no Vercel write.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
import shutil
import ssl
import subprocess
import sys
from urllib.parse import quote

import asyncpg
from production_neon_restore import DATABASE, HOST, NEW_HEAD, NEW_TABLES, OWNER, Stop

logging.disable(logging.CRITICAL)

RUNTIME = "intermind_app_runtime"
POOL_HOST = "ep-twilight-grass-baaqucnp-pooler.c-8.eu-central-1.aws.neon.tech"
VERCEL_PROJECT = "prj_qQeG1PbB8kUtH096VVcTVaTTMCou"
VERCEL_SCOPE = "aliyahs-projects-44a8830a"
GRANTS = {
    "recruiters": {"SELECT", "INSERT"},
    "recruiter_sessions": {"SELECT", "INSERT", "DELETE"},
    "rate_limit_events": {"SELECT", "INSERT", "DELETE"},
    "jobs": {"SELECT", "INSERT"},
    "interview_plans": {"SELECT", "INSERT", "UPDATE"},
    "candidates": {"SELECT", "INSERT", "DELETE"},
    "interview_sessions": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "interview_reports": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "activity_events": {"SELECT", "INSERT", "DELETE"},
}
SAFE_CONFIG = {
    "DATABASE_SSL_VERIFY_FULL": "true",
    "REQUIRE_DATABASE": "true",
    "SHARED_STATE_BACKEND": "postgres",
    "DATABASE_POOL_MODE": "null",
    "DATABASE_ECHO": "false",
    "RECRUITER_SESSION_COOKIE_SECURE": "true",
    "LLM_PROVIDER": "openai",
    "OPENAI_MODEL": "gpt-4o-mini",
    "OPENAI_TIMEOUT_SECONDS": "30",
    "OPENAI_MAX_RETRIES": "0",
    "REQUEST_DEADLINE_SECONDS": "105",
    "SPEECH_PROVIDER": "azure",
    "AZURE_SPEECH_AUTH": "key",
    "AZURE_SPEECH_REGION": "eastus",
    "ALLOWED_ORIGINS": "https://intermind-ai.vercel.app",
    "LOG_LEVEL": "INFO",
    "RETENTION_ENABLED": "false",
    "INTERVIEW_RETENTION_DAYS": "90",
}


def vercel_cli() -> str:
    cli = shutil.which("vercel.cmd")
    if not cli:
        raise Stop("Vercel CLI missing")
    return cli


def vercel_project_preflight() -> None:
    cli = vercel_cli()
    result = subprocess.run(
        [cli, "project", "inspect", "intermind-api-production", "--scope", VERCEL_SCOPE, "--json"],
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    if result.returncode:
        raise Stop("isolated Vercel backend project lookup failed")
    try:
        project = json.loads(result.stdout)
    except ValueError:
        raise Stop("isolated Vercel backend metadata invalid") from None
    if project.get("id") != VERCEL_PROJECT or project.get("rootDirectory") != "backend":
        raise Stop("isolated Vercel backend identity/root mismatch")
    result = subprocess.run(
        [cli, "env", "list", "--project", VERCEL_PROJECT, "--scope", VERCEL_SCOPE, "--json"],
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    if result.returncode:
        raise Stop("isolated Vercel backend environment lookup failed")
    try:
        payload = json.loads(result.stdout)
        items = payload.get("envs", payload) if isinstance(payload, dict) else payload
        keys = {item.get("key") or item.get("name") for item in items}
    except (TypeError, ValueError, AttributeError):
        raise Stop("isolated Vercel backend environment metadata invalid") from None
    if "DATABASE_URL" in keys or not {"OPENAI_API_KEY", "AZURE_SPEECH_KEY"} <= keys:
        raise Stop("isolated backend secret inventory differs from pre-cutover state")


def tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise Stop("verified TLS unavailable")
    return context


def validate_password_inputs(owner_password: str, runtime_password: str) -> None:
    """Reject unusable hidden input before opening a database connection.

    Errors identify only the failed field; they never include input contents or
    lengths. In particular, do not strip a password supplied by a manager.
    """
    if not owner_password:
        raise Stop("owner password absent; no connection attempted")
    validate_runtime_password(runtime_password)


def validate_runtime_password(runtime_password: str) -> None:
    """Validate only password policy, without disclosing password characteristics."""
    if len(runtime_password) < 32:
        raise Stop("runtime password below 32-character minimum; no connection attempted")
    if any(ord(char) < 32 for char in runtime_password):
        raise Stop("runtime password contains a control character; no connection attempted")


async def role_preflight(conn: asyncpg.Connection) -> None:
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
            raise Stop("direct owner identity or read-only preflight mismatch")
        head = await conn.fetchval("SELECT version_num FROM public.alembic_version")
        tables = {
            item["tablename"]
            for item in await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            )
        }
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)", RUNTIME
        )
        if head != NEW_HEAD or tables != NEW_TABLES or exists:
            raise Stop("migrated schema/head or runtime role absence mismatch")


async def verify_role(conn: asyncpg.Connection) -> None:
    role = await conn.fetchrow(
        "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, "
        "rolreplication, rolbypassrls, rolinherit FROM pg_roles WHERE rolname=$1",
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
        raise Stop("runtime role attributes not least privilege")
    membership = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles r "
        "ON r.oid=m.member WHERE r.rolname=$1)",
        RUNTIME,
    )
    if membership:
        raise Stop("runtime role has privileged membership")
    forbidden = await conn.fetchrow(
        "SELECT has_database_privilege($1, $2, 'CREATE') AS database_create, "
        "has_schema_privilege($1, 'public', 'CREATE') AS schema_create, "
        "has_table_privilege($1, 'public.alembic_version', 'SELECT') AS alembic_read, "
        "has_table_privilege($1, 'public.alembic_version', 'INSERT') AS alembic_write",
        RUNTIME, DATABASE,
    )
    if any(forbidden.values()):
        raise Stop("runtime role has CREATE or Alembic access")
    if not await conn.fetchval(
        "SELECT has_database_privilege($1,$2,'CONNECT')", RUNTIME, DATABASE
    ) or not await conn.fetchval(
        "SELECT has_schema_privilege($1,'public','USAGE')", RUNTIME
    ):
        raise Stop("runtime connection or schema privilege missing")
    for table, allowed in GRANTS.items():
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            actual = await conn.fetchval(
                "SELECT has_table_privilege($1,$2,$3)",
                RUNTIME, f"public.{table}", privilege,
            )
            if actual != (privilege in allowed):
                raise Stop("runtime table privileges differ from approved minimum")
    for privilege in ("USAGE", "SELECT", "UPDATE"):
        actual = await conn.fetchval(
            "SELECT has_sequence_privilege($1,$2,$3)",
            RUNTIME, "public.rate_limit_events_id_seq", privilege,
        )
        if actual != (privilege == "USAGE"):
            raise Stop("runtime sequence privilege mismatch")


async def create_and_check(owner_password: str, runtime_password: str) -> None:
    conn = await asyncpg.connect(
        host=HOST, port=5432, database=DATABASE, user=OWNER,
        password=owner_password, ssl=tls_context(), command_timeout=30,
        server_settings={"TimeZone": "UTC"},
    )
    try:
        await role_preflight(conn)
        print("PASS: migrated Neon production target and role absence verified")
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
                raise Stop("write transaction owner/target mismatch")
            quoted = await conn.fetchval("SELECT format('%L', $1::text)", runtime_password)
            await conn.execute(
                f"CREATE ROLE {RUNTIME} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB "
                f"NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {quoted}"
            )
            await conn.execute(f"GRANT CONNECT ON DATABASE {DATABASE} TO {RUNTIME}")
            await conn.execute(f"GRANT USAGE ON SCHEMA public TO {RUNTIME}")
            for table, privileges in GRANTS.items():
                await conn.execute(
                    f"GRANT {', '.join(sorted(privileges))} ON TABLE public.{table} TO {RUNTIME}"
                )
            await conn.execute(
                f"GRANT USAGE ON SEQUENCE public.rate_limit_events_id_seq TO {RUNTIME}"
            )
            await verify_role(conn)
    finally:
        await conn.close()
    print("PASS: production runtime role created with verified least privileges")
    await verify_runtime_login(runtime_password)


async def verify_runtime_login(runtime_password: str) -> None:
    runtime = await asyncpg.connect(
        host=POOL_HOST, port=5432, database=DATABASE, user=RUNTIME,
        password=runtime_password, ssl=tls_context(), command_timeout=20,
    )
    try:
        async with runtime.transaction(readonly=True):
            identity = await runtime.fetchrow(
                "SELECT current_database() AS db, session_user AS role, "
                "current_setting('transaction_read_only') AS read_only"
            )
            if (
                identity["db"] != DATABASE
                or identity["role"] != RUNTIME
                or identity["read_only"] != "on"
            ):
                raise Stop("pooled runtime TLS login/identity mismatch")
    finally:
        await runtime.close()


def vercel_add(name: str, value: str, *, secret: bool, force: bool = False) -> None:
    command = [
        vercel_cli(), "env", "add", name, "--project", VERCEL_PROJECT,
        "--scope", VERCEL_SCOPE, "--environment", "production",
        "--sensitive" if secret else "--no-sensitive", "--yes",
    ]
    if force:
        command.append("--force")
    result = subprocess.run(
        command, input=value, capture_output=True,
        text=True, timeout=40, check=False,
    )
    if result.returncode:
        raise Stop("isolated Vercel backend variable update failed for " + name)


def configure_backend(runtime_password: str) -> None:
    url = (
        f"postgresql+asyncpg://{RUNTIME}:{quote(runtime_password, safe='')}"
        f"@{POOL_HOST}/{DATABASE}"
    )
    for name, value in SAFE_CONFIG.items():
        vercel_add(name, value, secret=False, force=True)
    vercel_add("DATABASE_URL", url, secret=True)
    print("PASS: isolated Vercel backend Production settings configured; no deployment")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--role-only", action="store_true")
    mode.add_argument("--configure-only", action="store_true")
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise Stop("visible local terminal required for hidden credentials")
    if args.configure_only:
        vercel_project_preflight()
        print("PASS: exact isolated Vercel backend project and existing secret names verified")
        runtime_password = getpass.getpass("Existing production runtime password (hidden): ")
        validate_runtime_password(runtime_password)
        asyncio.run(verify_runtime_login(runtime_password))
        print("PASS: production pooled runtime login and read-only identity verified")
        configure_backend(runtime_password)
        return
    if not args.role_only:
        vercel_project_preflight()
        print("PASS: exact isolated Vercel backend project and existing secret names verified")
    owner_password = getpass.getpass("Neon production owner password (hidden): ")
    runtime_password = getpass.getpass("New runtime password from password manager (hidden): ")
    validate_password_inputs(owner_password, runtime_password)
    asyncio.run(create_and_check(owner_password, runtime_password))
    print("PASS: least-privilege Neon production role and pooled TLS login verified")
    if not args.role_only:
        configure_backend(runtime_password)


if __name__ == "__main__":
    try:
        main()
    except Stop as exc:
        print("STOP: " + str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        print("STOP: " + type(exc).__name__ + "; public Azure site unchanged")
        raise SystemExit(1) from None
