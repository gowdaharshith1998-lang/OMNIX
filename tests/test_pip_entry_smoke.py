"""Smoke tests for pip-entry runtime resolution.

These tests fail if the sys.path bootstrap in omnix.cli is removed or if
find-bugs is unregistered from the click group.

They use subprocess to simulate the actual pip-entry invocation, since
pytest itself runs from repo root where source-tree imports are easier to mask.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"


def _omnix_help(*subargs: str) -> tuple[int, str, str]:
    """Run `omnix <subargs> --help` via the pip-installed entry."""
    proc = subprocess.run(
        ["omnix", *subargs, "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_omnix_help_lists_findbugs():
    rc, out, err = _omnix_help()
    assert rc == 0, f"omnix --help failed: {err}"
    assert "find-bugs" in out, f"find-bugs not in top-level help:\n{out}"


def test_omnix_findbugs_help_succeeds():
    rc, out, err = _omnix_help("find-bugs")
    assert rc == 0, f"omnix find-bugs --help failed: {err}"


def test_omnix_axiom_export_vault_help_succeeds():
    rc, out, err = _omnix_help("axiom", "export-vault")
    assert rc == 0, (
        f"omnix axiom export-vault --help failed (sys.path bootstrap missing?):"
        f"\nstdout:{out}\nstderr:{err}"
    )


def test_omnix_axiom_verify_scan_help_succeeds():
    rc, out, err = _omnix_help("axiom", "verify-scan")
    assert rc == 0, (
        f"omnix axiom verify-scan --help failed (sys.path bootstrap missing?):"
        f"\nstdout:{out}\nstderr:{err}"
    )


def test_pip_context_imports_resolve():
    """Simulate pip-entry context, confirm omnix imports resolve after bootstrap."""
    rr = str(REPO_ROOT)
    sd = str(SRC_DIR)
    code = (
        "import importlib\n"
        "import sys\n"
        f"repo_root = {rr!r}\n"
        f"src_dir = {sd!r}\n"
        "sys.path = [p for p in sys.path if p not in (repo_root, src_dir)]\n"
        "sys.path.insert(0, src_dir)\n"
        "from omnix.cli import main  # noqa: F401 — triggers bootstrap in omnix.cli\n"
        "importlib.import_module('omnix.parser.skip_tracking')\n"
        "print('OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, f"bootstrap failed: {proc.stderr}\n{proc.stdout}"
    assert "OK" in proc.stdout
