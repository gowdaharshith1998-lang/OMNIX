"""Graph-backed caller-shape inference for Hypothesis strategies."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import hypothesis.strategies as sth
import pytest
from hypothesis import assume, given, settings
from hypothesis.errors import NonInteractiveExampleWarning
from hypothesis.strategies import composite

from verify import caller_shape, strategies

REPO = Path(__file__).resolve().parents[2]
FIX = Path(__file__).parent / "fixtures"
GRAPH = FIX / "sample_graph.db"
SYNTH = FIX / "caller_shape_int" / "synth.py"
_RAW_INT = caller_shape.aggregate_caller_arg_types(
    str(GRAPH), str(SYNTH), "target_merged", str(REPO)
)
_STRAT_INT = strategies.strategy_for_param(0, None, _RAW_INT, [])


@settings(max_examples=20, deadline=None)
@given(_STRAT_INT)
def test_int_only_infers_integers(v: object) -> None:
    assert 0 in _RAW_INT and "int" in _RAW_INT[0]
    assert isinstance(v, int)


_STRAT_MIX = strategies.strategy_for_param(0, None, {0: {"int": 2, "str": 1}}, [])


@composite
def _draw_mixed_both_kinds(draw) -> list:
    s = _STRAT_MIX
    for _n in (40, 80, 200):
        out = [draw(s) for _ in range(_n)]
        kinds = {type(x).__name__ for x in out}
        if "int" in kinds and "str" in kinds:
            return out
    assume(False)
    return out


@settings(max_examples=30, deadline=None)
@given(_draw_mixed_both_kinds())
def test_mixed_int_str_uses_one_of(samples: list) -> None:
    kinds = {type(x).__name__ for x in samples}
    assert "int" in kinds
    assert "str" in kinds


_STRAT_BROAD = strategies.strategy_for_param(0, None, {}, [])


@composite
def _draw_broad_diverse(draw) -> list:
    s = _STRAT_BROAD
    for n in (50, 120, 200):
        out = [draw(s) for _ in range(n)]
        if len({type(x).__name__ for x in out}) > 1:
            return out
    assume(False)
    return out


@settings(max_examples=30, deadline=None)
@given(_draw_broad_diverse())
def test_zero_callers_falls_back_to_broad(values: list) -> None:
    assert len({type(x).__name__ for x in values}) > 1


def test_many_caller_ids_sampled_not_oom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = monkeypatch
    import warnings

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
    con.execute("INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?)", (tid, "t", "function", rel_s, 1, 1, 1, None))
    for i in range(150):
        sid = f"{rel_s}::c{i}"
        con.execute("INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?)", (sid, f"c{i}", "function", rel_s, 1, 1, 1, None))
        con.execute("INSERT INTO edges (source_id, target_id, relationship) VALUES (?,?,?)", (sid, tid, "CALLS"))
    con.commit()
    con.close()
    raw = caller_shape.aggregate_caller_arg_types(
        str(dbp), str(fpath), "t", str(tmp_path)
    )
    assert raw is not None
    s0 = strategies.strategy_for_param(0, None, raw or {0: {}}, [])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=NonInteractiveExampleWarning)
        for _ in range(5):
            s0.example()  # type: ignore[union-attr]
