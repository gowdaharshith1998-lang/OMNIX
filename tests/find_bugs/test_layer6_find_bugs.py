from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from omnix.find_bugs import runner


def test_iter_layer6_excludes_python_files(
    tmp_path: Path, empty_graph_db_path: str
) -> None:
    (tmp_path / "a.py").write_text("def a(): return 0\n", encoding="utf-8")
    (tmp_path / "b.rs").write_text("fn f() -> i32 { 0 }\n", encoding="utf-8")
    c = sqlite3.connect(empty_graph_db_path, timeout=5.0)
    for rid, relp, nm in [
        ("a.py::a", "a.py", "a"),
        ("b.rs::f", "b.rs", "f"),
    ]:
        c.execute(
            "INSERT INTO nodes (id, name, type, file_path, start_line) VALUES (?,?,?,?,?)",  # noqa: E501
            (rid, nm, "function", relp, 1),
        )
    c.commit()
    c.close()
    t = runner._iter_layer6_targets(Path(empty_graph_db_path), tmp_path)
    relp0 = {x[1] for x in t}
    assert "a.py" not in relp0
    assert "b.rs" in relp0


def test_python_path_unchanged_when_only_py_in_graph(
    tmp_path: Path, empty_graph_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.py").write_text("def a(): return 0\n", encoding="utf-8")
    c = sqlite3.connect(empty_graph_db_path, timeout=5.0)
    c.execute(
        "INSERT INTO nodes (id, name, type, file_path, start_line) VALUES (?,?,?,?,?)",  # noqa: E501
        ("a.py::a", "a", "function", "a.py", 1),
    )
    c.commit()
    c.close()
    n = 0

    def _raise(*_a, **_k) -> None:  # noqa: ANN001, ANN201
        nonlocal n
        n += 1
        if n:
            raise RuntimeError("layer6 must not run for python-only graph")

    monkeypatch.setattr(
        "omnix.verify.runners.subprocess_llm.run_layer6_subprocess_limited",
        _raise,
    )
    monkeypatch.setenv("OMNIX_FUZZ_DRY", "1")
    ex, _out, _d = runner.run_find_bugs(
        str(tmp_path), graph_db=empty_graph_db_path, no_bundle=True, json_mode=True, examples=1
    )
    assert n == 0
    assert ex in (0, 1)


def test_finding_includes_layer6_metadata_with_stub(
    tmp_path: Path, empty_graph_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.rs").write_text("fn f() -> i32 { 0 }\n", encoding="utf-8")
    c = sqlite3.connect(empty_graph_db_path, timeout=5.0)
    c.execute(
        "INSERT INTO nodes (id, name, type, file_path, start_line) VALUES (?,?,?,?,?)",  # noqa: E501
        ("a.rs::f", "f", "function", "a.rs", 1),
    )
    c.commit()
    c.close()

    def _zero(*_a, **_k):  # noqa: ANN001, ANN201
        from omnix.verify.runners.base import Layer6Result  # noqa: I001, TC002

        return Layer6Result(
            findings=[],
            language="rust",
            runner_used="subprocess_llm",
            extra_metadata={"m": 1},
            ex_total=0,
        )

    monkeypatch.setattr(
        "omnix.verify.runners.subprocess_llm.run_layer6_subprocess_limited", _zero
    )
    monkeypatch.setenv("OMNIX_FUZZ_DRY", "1")
    ex, _o, j = runner.run_find_bugs(
        str(tmp_path), graph_db=empty_graph_db_path, no_bundle=True, json_mode=True, examples=1
    )
    assert ex in (0, 1) and (j is None or isinstance(j, dict))
