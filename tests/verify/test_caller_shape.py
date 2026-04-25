"""Graph-backed caller-shape inference for Hypothesis strategies."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from verify import caller_shape, strategies

REPO = Path(__file__).resolve().parents[2]
FIX = Path(__file__).parent / "fixtures"
GRAPH = FIX / "sample_graph.db"
SYNTH = FIX / "caller_shape_int" / "synth.py"


def test_int_only_infers_integers() -> None:
    raw = caller_shape.aggregate_caller_arg_types(
        str(GRAPH), str(SYNTH), "target_merged", str(REPO)
    )
    assert 0 in raw
    assert "int" in raw[0]
    s0 = strategies.strategy_for_param(0, None, raw, [])
    for _ in range(20):
        v = s0.example()  # type: ignore[union-attr]
        assert isinstance(v, int)


def test_mixed_int_str_uses_one_of() -> None:
    raw = {0: {"int": 2, "str": 1}}
    s0 = strategies.strategy_for_param(0, None, raw, [])
    kinds = {type(s0.example()).__name__ for _ in range(40)}  # type: ignore[union-attr]
    assert "int" in kinds
    assert "str" in kinds


def test_zero_callers_falls_back_to_broad() -> None:
    raw: dict = {}
    s0 = strategies.strategy_for_param(0, None, raw, [])
    kinds = {type(s0.example()).__name__ for _ in range(50)}  # type: ignore[union-attr]
    assert len(kinds) > 1


def test_many_caller_ids_sampled_not_oom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fpath = tmp_path / "f.py"
    fpath.write_text("def t(p, q):\n    return 0\n", encoding="utf-8")
    rel_s = fpath.name
    tid = f"{rel_s}::t"
    dbp = tmp_path / "g.db"
    con = sqlite3.connect(dbp)
    con.executescript(
        """
        CREATE TABLE nodes (id TEXT PRIMARY KEY, name TEXT, type TEXT,
        file_path TEXT, start_line INTEGER, end_line INTEGER, complexity INTEGER, metadata TEXT);
        CREATE TABLE edges (id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id TEXT, target_id TEXT, relationship TEXT, metadata TEXT);
        """
    )
    con.execute("INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?)", (tid, "t", "function", rel_s, 1, 1, 1, None))
    for i in range(150):
        sid = f"{rel_s}::c{i}"
        con.execute("INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?)", (sid, f"c{i}", "function", rel_s, 1, 1, 1, None))
        con.execute("INSERT INTO edges (source_id, target_id, relationship) VALUES (?,?,?)", (sid, tid, "CALLS"))
    con.commit()
    con.close()
    raw = caller_shape.aggregate_caller_arg_types(
        str(dbp), str(fpath), "t", str(tmp_path)
    )
    # Should complete (may be empty for missing AST bodies); key is no crash / OOM
    assert raw is not None
    s0 = strategies.strategy_for_param(0, None, raw or {0: {}}, [])
    _ = s0.example()  # type: ignore[union-attr]
