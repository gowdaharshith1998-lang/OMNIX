"""debt-19: find_bugs must not write Hypothesis / fuzz artifacts to CWD (repo root)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from find_bugs import path_safety
from find_bugs import runner

pytest.importorskip("hypothesis", reason="hypothesis required")

SAMPLE = Path(__file__).parent / "fixtures" / "sample_codebase"


def test_sanitize_filename_strips_nul_control_emoji_and_traversal() -> None:
    assert path_safety.sanitize_filename("a\x00b") is None
    s = path_safety.sanitize_filename("../etc/passwd")
    assert s is not None and s.startswith("h") and ".." not in s and "/" not in s
    t = path_safety.sanitize_filename("file-\N{SNOWMAN}.txt")
    assert t is not None and "\u2603" not in t
    dash = path_safety.sanitize_filename("-leading")
    assert dash is not None and not dash.startswith("-")


def test_safe_output_path_never_escapes_output_dir(tmp_path: Path) -> None:
    out = tmp_path / "safe_out"
    out.mkdir()
    p = path_safety.safe_output_path(out, "../../../etc/passwd")
    assert p is not None
    assert p.is_relative_to(out.resolve())
    assert path_safety.resolved_path_under(out, p) is not None


def test_find_bugs_scan_writes_hypothesis_under_codebase_not_omnix_cwd(
    tmp_path: Path,
    empty_graph_db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.environ.get("OMNIX_FIND_BUGS_INTEGRATION") == "0":
        pytest.skip("set OMNIX_FIND_BUGS_INTEGRATION=0 to skip")
    fake_omnix_install = tmp_path / "omnix_install_root"
    fake_omnix_install.mkdir()
    monkeypatch.setattr(runner, "_omnix_root", lambda: fake_omnix_install)

    dest = tmp_path / "sc"
    shutil.copytree(SAMPLE, dest)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".omnix" / "receipts").mkdir(parents=True, exist_ok=True)

    before_fake = set(fake_omnix_install.rglob("*")) if fake_omnix_install.exists() else set()
    ex, out, detail = runner.run_find_bugs(
        str(dest),
        examples=30,
        top=5,
        json_mode=True,
        no_bundle=True,
        include_private=False,
        max_file_size=1_000_000,
        graph_db=empty_graph_db_path,
    )
    assert ex == 1
    assert detail is not None
    assert "unsafe_div" in out
    # Subprocess verify uses cwd=<codebase>/.omnix/verify_workspace; Hypothesis must not write under fake install.
    assert not (fake_omnix_install / ".hypothesis").exists()
    after_fake = set(fake_omnix_install.rglob("*"))
    assert after_fake == before_fake
    hyp_db = dest / ".omnix" / "hypothesis"
    assert hyp_db.is_dir()
    assert (dest / ".omnix" / "verify_workspace").is_dir()


def test_verify_pbt_sqlite_path_does_not_create_files_in_parent_cwd(
    tmp_path: Path,
    empty_graph_db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression (debt-19 round 2): PBT targets that call sqlite3.connect(path) must not use CWD=repo root."""
    pytest.importorskip("hypothesis", reason="hypothesis required")
    from verify import runner as verify_runner

    pollution = tmp_path / "would_be_omnix_repo_root"
    pollution.mkdir()
    codebase = tmp_path / "proj"
    codebase.mkdir()
    ws = codebase / ".omnix" / "verify_workspace"
    ws.mkdir(parents=True, exist_ok=True)
    hyp = codebase / ".omnix" / "hypothesis"
    hyp.mkdir(parents=True, exist_ok=True)

    target = codebase / "sqlite_target.py"
    target.write_text(
        "def connect_any(db_path: str) -> None:\n"
        "    import sqlite3\n"
        "    sqlite3.connect(db_path).close()\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(pollution)
    monkeypatch.setenv("OMNIX_HYPOTHESIS_DATABASE_DIRECTORY", str(hyp.resolve()))
    monkeypatch.setenv("HYPOTHESIS_STORAGE_DIRECTORY", str(hyp.resolve()))

    before = set(pollution.iterdir())
    code, _out = verify_runner.run(
        str(target.resolve()),
        function="connect_any",
        examples=120,
        sign=False,
        output_format="json",
        graph_db_path=empty_graph_db_path,
        codebase_root=str(codebase.resolve()),
        no_receipt=True,
        omnix_root=str(tmp_path / "unused_omnix"),
        workspace_dir=str(ws.resolve()),
    )
    assert code in (0, 1, 2)
    assert set(pollution.iterdir()) == before


def test_findings_json_payload_intact_after_path_redirect(
    tmp_path: Path,
    empty_graph_db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.environ.get("OMNIX_FIND_BUGS_INTEGRATION") == "0":
        pytest.skip("set OMNIX_FIND_BUGS_INTEGRATION=0 to skip")
    dest = tmp_path / "sc2"
    shutil.copytree(SAMPLE, dest)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".omnix" / "receipts").mkdir(parents=True, exist_ok=True)
    ex, raw, detail = runner.run_find_bugs(
        str(dest),
        examples=25,
        top=5,
        json_mode=True,
        no_bundle=True,
        graph_db=empty_graph_db_path,
    )
    assert ex == 1 and detail is not None
    assert detail.get("kind") == "find_bugs"
    findings = detail.get("findings") or []
    assert isinstance(findings, list) and findings
    f0 = next(
        (
            f
            for f in findings
            if isinstance(f, dict)
            and f.get("function") == "unsafe_div"
            and f.get("dimension") != "filesystem_hygiene"
        ),
        None,
    )
    assert f0 is not None
    assert f0.get("severity_score") is not None
    assert isinstance(f0.get("failures"), list)
    # Double-parse raw JSON line to ensure serialization round-trip
    first = raw.strip().splitlines()[0]
    again = json.loads(first)
    assert again.get("findings")
