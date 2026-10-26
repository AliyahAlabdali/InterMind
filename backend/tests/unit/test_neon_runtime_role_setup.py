"""Pure local tests for the manually approved Neon staging role plan."""

from __future__ import annotations

import ssl

import pytest

from scripts import setup_neon_runtime_role as role_setup
from scripts.setup_neon_runtime_role import TABLE_GRANTS, direct_url, grant_sql

HOST = "ep-example.eu-central-1.aws.neon.tech"
BASE = "postgresql://intermind_staging_owner:synthetic%40password@" + HOST


@pytest.mark.parametrize(
    "snippet",
    [
        BASE + "/intermind_staging?sslmode=require&channel_binding=require",
        "psql '" + BASE + "/intermind_staging?sslmode=require'",
        'psql "' + BASE + '/intermind_staging?sslmode=verify-full"',
        BASE + "/intermind_staging\r\n",
    ],
)
def test_direct_owner_snippets_are_parsed_without_retaining_query_options(snippet):
    assert direct_url(snippet, HOST) == BASE + "/intermind_staging"


@pytest.mark.parametrize(
    "snippet",
    [
        BASE.replace(HOST, "ep-other.eu-central-1.aws.neon.tech") + "/intermind_staging",
        BASE.replace(HOST, "ep-example-pooler.eu-central-1.aws.neon.tech") + "/intermind_staging",
        BASE.replace("intermind_staging_owner", "intermind_runtime") + "/intermind_staging",
        BASE.replace("synthetic%40password", "") + "/intermind_staging",
        BASE + "/postgres",
        BASE + ":bad/intermind_staging",
        BASE + "/intermind_staging?sslmode=disable",
        BASE + "/intermind_staging?application_name=unexpected",
        "psql '" + BASE + "/intermind_staging' unexpected",
    ],
)
def test_wrong_or_malformed_target_fails_closed(snippet):
    with pytest.raises(ValueError):
        direct_url(snippet, HOST)


@pytest.mark.parametrize(
    ("snippet", "expected_label"),
    [
        (BASE + "/postgres", "database name"),
        (
            BASE.replace("intermind_staging_owner", "other_owner") + "/intermind_staging",
            "owner role",
        ),
        (BASE + ":5433/intermind_staging", "direct port"),
        (
            BASE.replace("synthetic%40password", "") + "/intermind_staging",
            "owner password presence",
        ),
        (BASE + "/intermind_staging?sslmode=disable", "TLS option"),
    ],
)
def test_input_errors_name_only_the_failed_field(snippet, expected_label):
    with pytest.raises(role_setup.InputValidationError) as error:
        direct_url(snippet, HOST)
    assert str(error.value) == expected_label
    assert "synthetic" not in str(error.value)
    assert HOST not in str(error.value)


def test_dashboard_direct_host_must_match_exactly():
    with pytest.raises(ValueError):
        direct_url(BASE + "/intermind_staging", "ep-other.eu-central-1.aws.neon.tech")
    with pytest.raises(ValueError):
        direct_url(BASE + "/intermind_staging", "ep-example-pooler.eu-central-1.aws.neon.tech")


def test_grants_are_tied_to_current_application_calls_only():
    assert TABLE_GRANTS == {
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
    statements = grant_sql()
    assert len(statements) == 12
    assert not any("alembic_version" in statement for statement in statements)
    assert not any("CREATE" in statement or "ALL" in statement for statement in statements)
    assert statements[-1] == (
        "GRANT USAGE ON SEQUENCE public.rate_limit_events_id_seq TO intermind_app_runtime"
    )


@pytest.mark.asyncio
async def test_apply_refuses_noninteractive_credential_input(monkeypatch):
    monkeypatch.setattr(role_setup.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(
        role_setup.getpass,
        "getpass",
        lambda _prompt: pytest.fail("hidden credential prompt must not run without a terminal"),
    )
    with pytest.raises(RuntimeError, match="visible local terminal"):
        await role_setup.apply()


@pytest.mark.asyncio
async def test_short_runtime_password_fails_before_connect(monkeypatch):
    monkeypatch.setattr(role_setup.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(role_setup.sys.stderr, "isatty", lambda: True)
    inputs = iter((HOST, BASE + "/intermind_staging", "synthetic-short"))
    monkeypatch.setattr(role_setup.getpass, "getpass", lambda _prompt: next(inputs))

    async def must_not_connect(**_kwargs):
        pytest.fail("validation must finish before any connection attempt")

    monkeypatch.setattr(role_setup.asyncpg, "connect", must_not_connect)
    with pytest.raises(role_setup.InputValidationError, match="runtime password policy"):
        await role_setup.apply()


def test_cli_reports_only_safe_field_for_short_password(monkeypatch, capsys):
    monkeypatch.setattr(role_setup.sys, "argv", ["setup_neon_runtime_role.py", "--apply"])
    monkeypatch.setattr(role_setup.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(role_setup.sys.stderr, "isatty", lambda: True)
    inputs = iter((HOST, BASE + "/intermind_staging", "synthetic-short-secret"))
    monkeypatch.setattr(role_setup.getpass, "getpass", lambda _prompt: next(inputs))
    with pytest.raises(SystemExit) as stopped:
        role_setup.main()
    assert stopped.value.code == 1
    output = capsys.readouterr().out
    assert "invalid runtime password policy" in output
    assert "No database connection attempted" in output
    assert "synthetic-short-secret" not in output


@pytest.mark.asyncio
async def test_asyncpg_value_error_is_labeled_prewrite_without_leaking_url(monkeypatch):
    monkeypatch.setattr(role_setup.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(role_setup.sys.stderr, "isatty", lambda: True)
    inputs = iter((HOST, BASE + "/intermind_staging", "synthetic-strong-password-1234567890"))
    monkeypatch.setattr(role_setup.getpass, "getpass", lambda _prompt: next(inputs))

    async def invalid_client_configuration(**_kwargs):
        raise ValueError("synthetic-secret-in-client-error")

    monkeypatch.setattr(role_setup.asyncpg, "connect", invalid_client_configuration)
    with pytest.raises(role_setup.ClientConfigurationError) as error:
        await role_setup.apply()
    assert str(error.value) == "asyncpg connection configuration"
    assert "synthetic-secret" not in str(error.value)


@pytest.mark.asyncio
async def test_status_uses_verified_tls_and_read_only_queries(monkeypatch, capsys):
    monkeypatch.setattr(role_setup.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(role_setup.sys.stderr, "isatty", lambda: True)
    inputs = iter((HOST, BASE + "/intermind_staging"))
    monkeypatch.setattr(role_setup.getpass, "getpass", lambda _prompt: next(inputs))
    calls = []

    class ReadOnlyTransaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    class FakeConnection:
        def transaction(self, *, readonly):
            assert readonly is True
            return ReadOnlyTransaction()

        async def fetchrow(self, sql):
            assert sql.startswith("SELECT ")
            calls.append("identity")
            return {"db": "intermind_staging", "role": "intermind_staging_owner", "read_only": "on"}

        async def fetchval(self, sql, role):
            assert sql.startswith("SELECT EXISTS ")
            assert role == "intermind_app_runtime"
            calls.append("role")
            return False

        async def close(self):
            calls.append("close")

    async def fake_connect(**options):
        assert options["server_settings"] == {"default_transaction_read_only": "on"}
        assert isinstance(options["ssl"], ssl.SSLContext)
        assert options["ssl"].check_hostname is True
        assert options["ssl"].verify_mode == ssl.CERT_REQUIRED
        return FakeConnection()

    monkeypatch.setattr(role_setup.asyncpg, "connect", fake_connect)
    await role_setup.status()
    assert calls == ["identity", "role", "close"]
    assert capsys.readouterr().out.strip() == "ROLE_STATUS: absent"
