"""Orchestrator integration: plan-only (R12), replay marker (R13 path)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("hypothesis")


def test_R12_plan_only_returns_budget_without_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".omnix" / "receipts").mkdir(parents=True, exist_ok=True)
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "mod.py").write_text(
        "def g(a: int, b: int) -> int:\n    return a // b\n",
        encoding="utf-8",
    )
    from omnix.find_bugs.runner import ensure_find_bugs_graph_db

    gdb, err = ensure_find_bugs_graph_db(tmp_path, None)
    assert err is None and gdb is not None
    ex, _txt, detail = __import__(
        "omnix.find_bugs.runner", fromlist=["run_find_bugs"]
    ).run_find_bugs(
        str(tmp_path),
        examples=10,
        json_mode=True,
        no_bundle=True,
        graph_db=str(gdb),
        plan_only=True,
        filesystem_hygiene=False,
    )
    assert ex == 0
    assert detail is not None
    summ = detail.get("summary") or {}
    plan = summ.get("turboscan_plan") or []
    assert isinstance(plan, list)
    assert any(str(row.get("function")) == "g" for row in plan)
