"""Verify frozen v1.1 evidence against historical source, independently of runtime."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL_ROOT = HERE.parent
SNAPSHOT = HERE / "historical_source_v1_1"
LOCK = HERE / "PROTOCOL_v1.1.lock.json"
MANIFEST = HERE / "artifacts" / "20261011T223751Z" / "RECOVERY_MANIFEST_v1.1.json"
# Original write-once manifest digest, also recorded in RECOVERY_MANIFEST_v1.1.sha256.
MANIFEST_SHA256 = "452762e16737933e4ee913e1141e1dc0dbb33bf570e06a8fd507434d743ebac5"
HISTORICAL_EVAL_SOURCES = frozenset({"audit.py", "latency.py"})


def historical_source_path(
    path: Path, *, snapshot_root: Path = SNAPSHOT, eval_root: Path = EVAL_ROOT
) -> Path:
    """Resolve only historically locked source to its raw-byte snapshot.

    Evaluation datasets, labels, manifests, locks, and results stay at their
    original locations so any alteration of those protected files remains visible.
    """
    resolved = path.resolve()
    app_root = (eval_root.parent / "app").resolve()
    if resolved.is_relative_to(app_root):
        return snapshot_root / "app" / resolved.relative_to(app_root)
    recovery_root = (eval_root / "recovery_v11").resolve()
    if resolved.parent == recovery_root and resolved.name in HISTORICAL_EVAL_SOURCES:
        return snapshot_root / "evals" / "recovery_v11" / resolved.name
    return path


def _sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(f"Historical provenance file unavailable: {path}") from exc


def _json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Historical provenance JSON invalid: {path}") from exc


def verify_historical_provenance(
    *,
    snapshot_root: Path = SNAPSHOT,
    lock_path: Path = LOCK,
    manifest_path: Path = MANIFEST,
    eval_root: Path = EVAL_ROOT,
) -> dict[str, str | int]:
    """Check raw historical bytes against the unchanged v1.1 lock and manifest.

    Runtime application files are deliberately never read. Frozen evaluation inputs
    remain at their original paths and are still checked against the original lock.
    No line-ending or other content normalization occurs during verification.
    """
    if _sha(manifest_path) != MANIFEST_SHA256:
        raise ValueError("Historical recovery manifest changed")
    manifest = _json(manifest_path)
    if manifest.get("version") != "1.1" or manifest.get("source_status") != "incomplete":
        raise ValueError("Historical recovery manifest status changed")
    lock_digest = _sha(lock_path)
    if lock_digest != manifest["recovery_files_sha256"]["PROTOCOL_v1.1.lock.json"]:
        raise ValueError("Historical recovery protocol lock changed")
    lock = _json(lock_path)
    if lock.get("version") != "1.1" or lock.get("status") != "frozen":
        raise ValueError("Historical recovery protocol is not frozen")

    app_count = 0
    for relative, expected in lock["sha256"].items():
        path = historical_source_path(
            eval_root / relative, snapshot_root=snapshot_root, eval_root=eval_root
        )
        if relative.startswith("../app/"):
            app_count += 1
        if _sha(path) != expected:
            raise ValueError(f"Historical recovery source changed: {relative}")

    for relative, expected in manifest["source_code_sha256"].items():
        if not (relative.startswith("app/") or relative.startswith("evals/")):
            raise ValueError(f"Unexpected historical source path: {relative}")
        path = historical_source_path(
            eval_root.parent / relative, snapshot_root=snapshot_root, eval_root=eval_root
        )
        if _sha(path) != expected:
            raise ValueError(f"Historical recovery manifest source changed: {relative}")

    return {
        "version": "1.2-historical-provenance",
        "historical_lock_sha256": lock_digest,
        "historical_manifest_sha256": MANIFEST_SHA256,
        "locked_files_verified": len(lock["sha256"]),
        "historical_app_files_verified": app_count,
        "historical_eval_files_verified": len(HISTORICAL_EVAL_SOURCES),
        "manifest_source_files_verified": len(manifest["source_code_sha256"]),
    }
