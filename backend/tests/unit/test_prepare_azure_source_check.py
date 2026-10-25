"""The launcher pins remote raw bytes; these tests make no network calls."""

from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import prepare_azure_source_check as prepare  # noqa: E402


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def test_immutable_raw_bytes_must_match_exact_git_blob(monkeypatch):
    committed = b"print('synthetic')\n"
    revision = "a" * 40

    def git(*args):
        if args == ("branch", "--show-current"):
            return b"staging/vercel-neon\n"
        if args == ("status", "--porcelain", "--", prepare.SOURCE):
            return b""
        if args == ("rev-parse", "HEAD"):
            return revision.encode() + b"\n"
        if args[0] == "ls-remote":
            return revision.encode() + b"\trefs/heads/staging/vercel-neon\n"
        if args == ("show", f"{revision}:{prepare.SOURCE}"):
            return committed
        raise AssertionError(args)

    monkeypatch.setattr(prepare, "git", git)
    monkeypatch.setattr(
        prepare.urllib.request, "urlopen", lambda *_args, **_kw: Response(committed),
    )
    url, digest = prepare.pinned_source()
    assert f"/{revision}/" in url
    assert digest == hashlib.sha256(committed).hexdigest()
    monkeypatch.setattr(
        prepare.urllib.request, "urlopen", lambda *_args, **_kw: Response(committed[:-1]),
    )
    with pytest.raises(prepare.Stop, match="differs"):
        prepare.pinned_source()


def test_launcher_rejects_unpushed_revision_before_downloading(monkeypatch):
    def git(*args):
        if args[0] == "branch":
            return b"staging/vercel-neon\n"
        if args[0] == "status":
            return b""
        if args[0] == "rev-parse":
            return b"a" * 40 + b"\n"
        if args[0] == "ls-remote":
            return b"b" * 40 + b"\trefs/heads/staging/vercel-neon\n"
        raise AssertionError(args)

    monkeypatch.setattr(prepare, "git", git)
    with pytest.raises(prepare.Stop, match="not the remote"):
        prepare.pinned_source()
