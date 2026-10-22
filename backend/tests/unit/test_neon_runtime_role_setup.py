"""Pure local tests for the manually approved Neon staging role plan."""

from __future__ import annotations

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
