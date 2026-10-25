"""Synthetic checks for the production role helper; no database or Vercel access."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import production_runtime_role as role  # noqa: E402


@pytest.mark.parametrize(
    ("owner", "runtime", "expected"),
    [
        ("", "x" * 32, "owner password absent"),
        ("owner", "x" * 31, "runtime password below 32-character minimum"),
        ("owner", "x" * 32 + "\r", "runtime password contains a control character"),
    ],
)
def test_invalid_hidden_inputs_fail_before_connection(owner, runtime, expected):
    with pytest.raises(role.Stop, match=expected) as error:
        role.validate_password_inputs(owner, runtime)
    assert runtime not in str(error.value)
    assert owner not in str(error.value) or not owner


def test_valid_printable_password_is_accepted_without_normalization():
    role.validate_password_inputs("owner", "x" * 31 + " ")


def test_runtime_role_targets_only_separate_neon_production():
    assert role.DATABASE == "intermind_production"
    assert role.OWNER == "intermind_production_owner"
    assert role.RUNTIME == "intermind_app_runtime"
    assert role.POOL_HOST.endswith("-pooler.c-8.eu-central-1.aws.neon.tech")
    assert role.SAFE_CONFIG["RETENTION_ENABLED"] == "false"
    assert "alembic_version" not in role.GRANTS


def test_isolated_backend_config_uses_pooled_runtime_url_last(monkeypatch):
    changes = []
    monkeypatch.setattr(
        role,
        "vercel_add",
        lambda name, value, **options: changes.append((name, value, options)),
    )
    role.configure_backend("synthetic@password" + "x" * 24)
    assert {name for name, _, _ in changes} == set(role.SAFE_CONFIG) | {"DATABASE_URL"}
    assert changes[-1][0] == "DATABASE_URL"
    assert changes[-1][2] == {"secret": True}
    assert changes[-1][1].startswith(
        "postgresql+asyncpg://intermind_app_runtime:synthetic%40password"
    )
    assert changes[-1][1].endswith("/intermind_production")
    assert all(name != "DATABASE_URL" for name, _, _ in changes[:-1])
