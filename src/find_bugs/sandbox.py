"""
Sandbox for Layer 7 auto-fix (P26): all writes under ``/tmp`` only.
Cleanup is always attempted in ``finally`` (P30).
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path

_LOG = logging.getLogger("omnix.find_bugs.sandbox")


def create_fix_sandbox() -> Path:
    """``tempfile.mkdtemp(prefix='omnix_fix_', dir='/tmp')`` — P26."""
    d = tempfile.mkdtemp(prefix="omnix_fix_", dir="/tmp")
    p = Path(d)
    p.chmod(0o700)
    return p.resolve()


def cleanup_sandbox(sandbox: Path | str) -> bool:
    """
    ``shutil.rmtree`` with best-effort. Returns True on full success (P30).
    """
    sp = Path(sandbox)
    try:
        rp = sp.resolve()
    except OSError as e:  # pragma: no cover
        _LOG.warning("cleanup: resolve %s: %s", sandbox, e)
        return False
    if not str(rp).startswith("/tmp/") and str(rp) != "/tmp":  # noqa: SIM108, SIM114
        # Refuse to remove paths outside /tmp (safety)
        _LOG.warning("cleanup: refuse non-tmp path %s", rp)
        return False
    try:
        shutil.rmtree(rp, ignore_errors=False)
        return True
    except OSError as e:
        _LOG.warning("cleanup: rmtree %s: %s", rp, e)
        return False


def copy_file_into_sandbox(
    *,
    repo_root: Path,
    rel_path: str,
    sandbox_root: Path,
) -> Path:
    """
    Copy one source file from the user repo into the sandbox mirror path.
    **Read** from user disk; **write** only under *sandbox_root* (P26, P27).
    """
    src = (repo_root / rel_path).resolve()
    try:
        src.relative_to(repo_root.resolve())
    except ValueError as e:  # noqa: RUF100
        raise ValueError("path escapes repo") from e
    if not src.is_file():
        raise FileNotFoundError(str(src))
    dst = (sandbox_root / rel_path).resolve()
    try:
        dst.relative_to(sandbox_root.resolve())
    except ValueError as e:
        raise ValueError("bad dst") from e
    dst.parent.mkdir(parents=True, exist_ok=True)
    # copy into sandbox — destination path is under /tmp/omnix_fix_*
    shutil.copy2(src, dst)  # noqa: S108 — dst is under sandbox
    return dst


def copy_project_manifests(repo_root: Path, sandbox_root: Path) -> list[str]:
    """
    Copy minimal project files for test discovery. Only **to** *sandbox_root* (P26).
    """
    rel_names = [
        "pyproject.toml",
        "pytest.ini",
        "tox.ini",
        "setup.cfg",
        "Cargo.toml",
        "Cargo.lock",
        "go.mod",
        "go.sum",
        "pom.xml",
        "package.json",
        "package-lock.json",
    ]
    copied: list[str] = []
    for n in rel_names:
        p = repo_root / n
        if p.is_file():
            dst = sandbox_root / n
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)  # noqa: S108
            copied.append(n)
    for cs in sorted(repo_root.glob("*.csproj")):
        dst = sandbox_root / cs.name
        shutil.copy2(cs, dst)  # noqa: S108
        copied.append(cs.name)
        break
    return copied


def copy_shallow_test_artifacts(repo_root: Path, sandbox_root: Path) -> list[str]:
    """
    Best-effort copy of `tests/`, `test_*.py` at repo root, one level, for
    meaningful baseline. Writes only under *sandbox_root* (P26).
    """
    out: list[str] = []
    tdir = repo_root / "tests"
    if tdir.is_dir():
        dst = sandbox_root / "tests"
        shutil.copytree(tdir, dst, symlinks=False, ignore=None)  # noqa: S108, S603, SIM103
        out.append("tests/")
    for p in sorted(repo_root.glob("test_*.py")):
        if p.is_file():
            d = sandbox_root / p.name
            shutil.copy2(p, d)  # noqa: S108, SIM103, SIM102
            out.append(p.name)
    return out


def assert_write_allowed(path: Path) -> None:
    """Reject writes that would land outside a ``/tmp`` tree (P26)."""
    try:
        r = path.resolve()
    except OSError as e:  # pragma: no cover
        raise ValueError("bad path") from e
    s = str(r)
    if not s.startswith("/tmp/") and s != "/tmp":
        raise ValueError(f"P26: write outside /tmp rejected: {s}")
