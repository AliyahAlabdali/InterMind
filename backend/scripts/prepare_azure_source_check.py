"""Print two short, pinned Azure SSH commands for the read-only source gate.

Requires the authenticated private backup bundle and a reviewed, pushed
``staging/vercel-neon`` commit. Prints hashes only, never credentials or rows.
"""

from __future__ import annotations

import hashlib
import subprocess
import urllib.request
from pathlib import Path

from azure_source_fingerprint import summary_digest
from production_neon_restore import archive_manifest

ROOT = Path(__file__).resolve().parents[2]
BRANCH = "staging/vercel-neon"
SOURCE = "backend/scripts/azure_source_fingerprint.py"
REMOTE = "https://raw.githubusercontent.com/AliyahAlabdali/InterMind"
TEMP = "/tmp/intermind-azure-source-check.py"


class Stop(RuntimeError):
    """A fixed, non-sensitive failure reason."""


def git(*args: str) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, check=False, timeout=30,
    )
    if result.returncode:
        raise Stop("Git source or remote verification failed")
    return result.stdout


def pinned_source() -> tuple[str, str]:
    if git("branch", "--show-current").decode("ascii").strip() != BRANCH:
        raise Stop("staging branch identity mismatch")
    if git("status", "--porcelain", "--", SOURCE):
        raise Stop("comparison script has uncommitted changes")
    revision = git("rev-parse", "HEAD").decode("ascii").strip()
    if len(revision) != 40:
        raise Stop("Git revision format mismatch")
    remote_revision = git("ls-remote", "origin", "refs/heads/" + BRANCH).decode("ascii").strip()
    if remote_revision.split("\t", 1)[0] != revision:
        raise Stop("reviewed commit is not the remote staging branch head")
    committed = git("show", f"{revision}:{SOURCE}")
    url = f"{REMOTE}/{revision}/{SOURCE}"
    with urllib.request.urlopen(url, timeout=20) as response:
        received = response.read(100_000)
    if not received or len(received) >= 100_000 or received != committed:
        raise Stop("immutable GitHub source differs from reviewed Git blob")
    return url, hashlib.sha256(received).hexdigest()


def main() -> None:
    url, script_hash = pinned_source()
    _, manifest = archive_manifest()
    expected = summary_digest(
        manifest["table_counts"], manifest["row_fingerprints_md5"],
    )
    print("PASS: exact pushed source, HTTPS bytes, and private encrypted backup verified")
    print("Run these two short commands in the authenticated Azure main-container SSH shell:")
    print(f"curl -fLsS --max-time 30 -o {TEMP} {url}")
    print(
        f"echo '{script_hash}  {TEMP}' | sha256sum -c - "
        f"&& python -B {TEMP} --expected-sha256 {expected}"
    )
    print(f"Then remove only the temporary script: rm -f {TEMP}")


if __name__ == "__main__":
    try:
        main()
    except (Stop, OSError, ValueError) as exc:
        if isinstance(exc, Stop):
            print("STOP: " + str(exc))
        else:
            print("STOP: sanitized " + type(exc).__name__)
        raise SystemExit(1) from None
