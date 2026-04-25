"""End-to-end find_bugs on a tiny fake codebase (one known PBT failure)."""

from __future__ import annotations

import json
import os
import shutil
import pytest
from pathlib import Path

pytest.importorskip("hypothesis", reason="hypothesis required")

from find_bugs import runner

SAMPLE = Path(__file__).parent / "fixtures" / "sample_codebase"


def test_one_finding_unsafe_div(
    tmp_path: Path, empty_graph_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.environ.get("OMNIX_FIND_BUGS_INTEGRATION") == "0":
        pytest.skip("set OMNIX_FIND_BUGS_INTEGRATION=0 to skip")
    dest = tmp_path / "sc"
    shutil.copytree(SAMPLE, dest)
    rdir = tmp_path / "rcpt"
    rdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".omnix" / "receipts").mkdir(parents=True, exist_ok=True)
    ex, out, detail = runner.run_find_bugs(
        str(dest),
        examples=40,
        top=5,
        json_mode=False,
        no_bundle=False,
        include_private=False,
        max_file_size=1_000_000,
        graph_db=empty_graph_db_path,
    )
    assert ex == 1
    assert "unsafe_div" in out
    rfiles = list((tmp_path / ".omnix" / "receipts").glob("find_bugs_*.json"))
    assert rfiles, "bundle should be written"
    data = json.loads(rfiles[0].read_text(encoding="utf-8"))
    assert data.get("kind") == "find_bugs"
    names = [f.get("function") for f in data.get("findings", [])]
    assert "unsafe_div" in names
    assert detail is None or isinstance(detail, dict)


def test_skip_self_recursion(
    tmp_path: Path, empty_graph_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.environ.get("OMNIX_FIND_BUGS_INTEGRATION") == "0":
        pytest.skip("set OMNIX_FIND_BUGS_INTEGRATION=0 to skip")
    d = tmp_path / "ep"
    d.mkdir()
    m = d / "script.py"
    m.write_text(
        'def main():\n    return 0\n\nif __name__ == "__main__":\n    main()\n',
        encoding="utf-8",
    )
    rdir = tmp_path / "rcpt"
    rdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".omnix" / "receipts").mkdir(parents=True, exist_ok=True)
    ex, out, jdetail = runner.run_find_bugs(
        str(d),
        examples=5,
        top=5,
        json_mode=True,
        no_bundle=True,
        include_private=False,
        max_file_size=1_000_000,
        graph_db=empty_graph_db_path,
    )
    assert "RecursionError" not in out
    assert "maximum recursion" not in out.lower()
    assert ex == 0
    assert jdetail is not None
    sm = jdetail.get("skipped_main") or []
    names = [x.get("function") for x in sm if isinstance(x, dict)]
    assert "main" in names
    findings = jdetail.get("findings") or []
    fns = {f.get("function") for f in findings if isinstance(f, dict)}
    assert "main" not in fns
    assert (jdetail.get("summary") or {}).get("skipped_main_count", 0) >= 1
