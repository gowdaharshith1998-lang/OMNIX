"""OMNIX Studio storage paths — global ``~/.omnix`` and per-project ``.omnix/``."""

from __future__ import annotations

import os
from pathlib import Path

_GLOBAL_ENV = "OMNIX_STUDIO_OMNIX_DIR"


def global_omnix_dir() -> Path:
    """``~/.omnix`` (or OMNIX_STUDIO_OMNIX_DIR in tests)."""
    raw = os.environ.get(_GLOBAL_ENV, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".omnix").resolve()


def ensure_global_omnix_dir() -> Path:
    d = global_omnix_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def project_omnix_dir(project_path: str | Path) -> Path:
    """``<project>/.omnix`` (resolved)."""
    return (Path(project_path).expanduser().resolve() / ".omnix")


def ensure_project_omnix_dir(project_path: str | Path) -> Path:
    d = project_omnix_dir(project_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def project_graph_db_path(project_path: str | Path) -> Path:
    return ensure_project_omnix_dir(project_path) / "omnix.db"


def sessions_dir() -> Path:
    return ensure_global_omnix_dir() / "sessions"


def session_path(workspace_id: str) -> Path:
    return sessions_dir() / workspace_id
