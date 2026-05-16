"""Layer 6: incremental scan file selection."""

from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any

from omnix.scan.turboscan.types import turboscan_last_scan_path

_LOG = logging.getLogger("omnix.scan.turboscan.incremental")


def _load_last_scan(repo_root: Path) -> dict[str, Any] | None:
    p = turboscan_last_scan_path(repo_root)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        _LOG.warning("incremental: could not read last scan state %s: %s", p, e)
        return None


def _in_git_repo(root: Path) -> bool:
    return (root / ".git").exists()


def file_modified_since_last_scan(repo_root: Path, relpath: str) -> bool:
    """R6(a): git log since last ISO timestamp, else False."""
    st = _load_last_scan(repo_root)
    if not st:
        return True
    since = str(st.get("iso_utc") or "").strip()
    if not since:
        return True
    root = repo_root.resolve()
    if not _in_git_repo(root):
        return True
    try:
        r = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                "-1",
                f"--since={since}",
                "--",
                relpath,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        _LOG.debug("incremental git log failed: %s", e)
        return True
    return r.returncode == 0 and bool((r.stdout or "").strip())


def file_modified_by_mtime(repo_root: Path, relpath: str, last_mtime: float) -> bool:
    """R6(b): mtime fallback when not in git."""
    p = (repo_root / relpath).resolve()
    try:
        mt = p.stat().st_mtime
    except OSError:
        return True
    return mt > last_mtime


def filter_incremental_paths(
    repo_root: Path,
    paths: list[Path],
    *,
    relpos_fn: Any,
) -> list[Path]:
    """Keep only files that changed since last successful scan."""
    repo_root = repo_root.resolve()
    st = _load_last_scan(repo_root)
    if not st:
        return paths
    if _in_git_repo(repo_root):
        out: list[Path] = []
        for p in paths:
            rel = relpos_fn(p, repo_root)
            if file_modified_since_last_scan(repo_root, rel):
                out.append(p)
        return out
    last_mtime = float(st.get("mtime_epoch") or 0)
    return [
        p
        for p in paths
        if file_modified_by_mtime(repo_root, relpos_fn(p, repo_root), last_mtime)
    ]


def write_last_green_scan(repo_root: Path) -> None:
    """Persist scan marker after successful completion."""
    from datetime import datetime, timezone

    root = repo_root.resolve()
    d = turboscan_last_scan_path(root).parent
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        _LOG.error("incremental: cannot create state dir %s: %s", d, e)
        raise
    iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {"iso_utc": iso, "mtime_epoch": time.time()}
    turboscan_last_scan_path(root).write_text(
        json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8"
    )
