"""Integration: filesystem hygiene wired through find_bugs + verify."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("hypothesis", reason="hypothesis required")

from omnix.find_bugs.runner import run_find_bugs_with_hygiene  # noqa: E402

# Deterministic leak: ignores fuzzed inputs and always mkdirs under OMNIX_FS_HYGIENE_REPO_ROOT
# so the hygiene detector must fire without relying on Hypothesis luck.
_LEAKY_PY = (
    "from pathlib import Path\n"
    "import os\n"
    "def mkdir_garbage_omnix(codebase: str, name: str) -> None:\n"
    "    raw = os.environ.get('OMNIX_FS_HYGIENE_REPO_ROOT', '').strip()\n"
    "    root = Path(raw).resolve() if raw else Path(codebase).resolve()\n"
    "    (root / 'slice17b_hygiene_probe' / '.omnix').mkdir(parents=True, exist_ok=True)\n"
)


def test_R5_detects_known_leak_in_fixture_function(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    empty_graph_db_path: str,
) -> None:
    """R5 (synthetic): deterministic leak under repo root → HIGH hygiene finding."""
    if os.environ.get("OMNIX_FIND_BUGS_INTEGRATION") == "0":
        pytest.skip("set OMNIX_FIND_BUGS_INTEGRATION=0 to skip")

    dest = tmp_path / "ws"
    dest.mkdir()
    pkg = dest / "leak_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "leaky.py").write_text(_LEAKY_PY, encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".omnix" / "receipts").mkdir(parents=True, exist_ok=True)

    ex, _out, detail = run_find_bugs_with_hygiene(
        str(dest),
        examples=30,
        top=30,
        json_mode=True,
        no_bundle=True,
        include_private=False,
        max_file_size=1_000_000,
        graph_db=empty_graph_db_path,
        filesystem_hygiene=True,
    )
    assert detail is not None
    findings = detail.get("findings") or []
    hy = [
        f
        for f in findings
        if isinstance(f, dict) and f.get("dimension") == "filesystem_hygiene"
    ]
    assert hy, f"expected filesystem_hygiene findings, exit={ex} findings={findings!r}"
    assert any(str(h.get("severity")).upper() in ("HIGH", "MEDIUM") for h in hy)


def test_R5_omnix_self_scan_flags_debt19_function(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    empty_graph_db_path: str,
) -> None:
    """R5: debt-19-shaped leak (garbage dirname + .omnix) detected on mini workspace."""
    if os.environ.get("OMNIX_FIND_BUGS_INTEGRATION") == "0":
        pytest.skip("set OMNIX_FIND_BUGS_INTEGRATION=0 to skip")

    dest = tmp_path / "mini_omnix"
    dest.mkdir()
    pkg = dest / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "debt19_like.py").write_text(
        "from pathlib import Path\n"
        "import os\n"
        "def mkdir_codebase_garbage_omnix(codebase: str, segment: str) -> None:\n"
        "    raw = os.environ.get('OMNIX_FS_HYGIENE_REPO_ROOT', '').strip()\n"
        "    root = Path(raw).resolve() if raw else Path(codebase).resolve()\n"
        "    (root / 'slice17b_debt19_probe' / '.omnix').mkdir(parents=True, exist_ok=True)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".omnix" / "receipts").mkdir(parents=True, exist_ok=True)

    ex, raw, detail = run_find_bugs_with_hygiene(
        str(dest),
        examples=25,
        top=30,
        json_mode=True,
        no_bundle=True,
        include_private=False,
        max_file_size=1_000_000,
        graph_db=empty_graph_db_path,
        filesystem_hygiene=True,
    )
    assert detail is not None
    findings = detail.get("findings") or []
    hy = [
        f for f in findings if isinstance(f, dict) and f.get("dimension") == "filesystem_hygiene"
    ]
    assert hy, json.dumps({"exit": ex, "raw_head": raw[:2000], "findings": findings[:5]}, indent=2)
    assert any(
        "mkdir_codebase_garbage_omnix" in str(h.get("target_function", ""))
        or "mkdir_codebase_garbage_omnix" in str(h.get("function", ""))
        for h in hy
    )
    assert any(str(h.get("severity")).upper() in ("HIGH", "MEDIUM") for h in hy)
