"""Discover ``.py`` source files to scan, honoring ignores and a simple .gitignore."""

from __future__ import annotations

import ast
import logging
import os
from collections.abc import Iterator
from pathlib import Path

_LOG = logging.getLogger("find_bugs.walker")

IGNORE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        ".tox",
        ".pytest_cache",
        ".mypy_cache",
    }
)


def _load_gitignore(root: Path) -> list[str]:
    p = root / ".gitignore"
    if not p.is_file():
        return []
    out: list[str] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        t = t.split("#", 1)[0].strip()
        t = t.rstrip("/")
        if t:
            out.append(t)
    return out


def _path_matches_prefix(rel: Path, prefixes: list[str]) -> bool:
    s_alt = str(rel).replace(os.sep, "/")
    for p0 in prefixes:
        p = p0.replace(os.sep, "/")
        if s_alt == p or s_alt.startswith(f"{p}/"):
            return True
    return False


def _skip_dir_name(name: str) -> bool:
    if name in IGNORE_DIRS:
        return True
    if name.endswith(".egg-info"):
        return True
    return False


def _iter_raw_python_paths(root: Path, max_size: int) -> Iterator[Path]:
    root = root.resolve()
    gignore = _load_gitignore(root)
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        dirnames[:] = [d for d in dirnames if not _skip_dir_name(d)]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            full = Path(dirpath) / fname
            try:
                rel = full.relative_to(root)
            except ValueError:
                continue
            if _path_matches_prefix(rel, gignore):
                continue
            try:
                st = full.stat()
            except OSError:
                continue
            if st.st_size > max_size:
                continue
            yield full


# Warn once per path per process (avoids log spam if discovery is re-run)
_warned_unparseable: set[str] = set()


def walk_python_files(
    root: Path, max_size: int = 1_000_000, *, require_parseable: bool = True
) -> Iterator[Path]:
    """
    Walk ``.py`` files under *root* with common dev dirs and simple ``.gitignore`` rules.

    When *require_parseable* is true (default), unparseable files are skipped
    and a warning is logged (at most once per path in this process).
    """
    for full in _iter_raw_python_paths(root, max_size):
        if not require_parseable:
            yield full
            continue
        try:
            ast.parse(
                full.read_text(encoding="utf-8", errors="replace"), filename=str(full)
            )
        except (SyntaxError, OSError) as e:
            k = str(full.resolve())
            if k not in _warned_unparseable:
                _warned_unparseable.add(k)
                _LOG.warning("skip unparseable %s: %s", full, e)
            continue
        yield full


def scan_codebase_sources(
    root: Path, max_size: int = 1_000_000
) -> tuple[list[Path], int, int]:
    """One tree walk: parseable paths, n_skipped unparseable, n_skipped too big."""
    n_big = 0
    n_unparse = 0
    parseable: list[Path] = []
    root = root.resolve()
    gignore = _load_gitignore(root)
    for dirpath, dirnames, filenames in os.walk(
        root, topdown=True, followlinks=False
    ):
        dirnames[:] = [d for d in dirnames if not _skip_dir_name(d)]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            full = Path(dirpath) / fname
            try:
                rel = full.relative_to(root)
            except ValueError:
                continue
            if _path_matches_prefix(rel, gignore):
                continue
            try:
                st = full.stat()
            except OSError:
                continue
            if st.st_size > max_size:
                n_big += 1
                continue
            try:
                ast.parse(
                    full.read_text(encoding="utf-8", errors="replace"),
                    filename=str(full),
                )
            except (SyntaxError, OSError) as e:
                n_unparse += 1
                k = str(full.resolve())
                if k not in _warned_unparseable:
                    _warned_unparseable.add(k)
                    _LOG.warning("skip unparseable %s: %s", full, e)
                continue
            parseable.append(full)
    return parseable, n_unparse, n_big


def count_skipped_due_to_size(root: Path, max_size: int) -> int:
    """``.py`` candidates excluded only because of *max_size* (pre-parse)."""
    root = root.resolve()
    n = 0
    gignore = _load_gitignore(root)
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        dirnames[:] = [d for d in dirnames if not _skip_dir_name(d)]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            full = Path(dirpath) / fname
            try:
                rel = full.relative_to(root)
            except ValueError:
                continue
            if _path_matches_prefix(rel, gignore):
                continue
            try:
                st = full.stat()
            except OSError:
                continue
            if st.st_size > max_size:
                n += 1
    return n
