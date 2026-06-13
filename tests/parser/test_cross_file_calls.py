"""Cross-file CALLS edge resolution in the production ingest path.

Regression guard: each file is parsed in an isolated per-file store, so without
the global second pass a call from one module into another never produces a
CALLS edge. The unified ingest (`omnix analyze` / Studio) must resolve them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnix.graph.store import GraphStore
from omnix.parser import ingest_dispatch as ind


def _calls(store: GraphStore) -> list[tuple[str, str, str, str]]:
    nodes = {n.id: n for n in store.iter_all_nodes()}
    out = []
    for e in store.iter_all_edges():
        if e.relationship != "CALLS":
            continue
        src = nodes.get(e.source_id)
        dst = nodes.get(e.target_id)
        out.append(
            (
                e.source_id,
                e.target_id,
                src.file_path if src else "?",
                dst.file_path if dst else "?",
            )
        )
    return out


def test_python_cross_file_call_edge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIX_INGEST_WORKERS", "1")
    src = tmp_path / "proj"
    src.mkdir()
    (src / "lib.py").write_text("def helper(x):\n    return x + 1\n", encoding="utf-8")
    (src / "app.py").write_text(
        "from lib import helper\n\ndef main():\n    return helper(41)\n",
        encoding="utf-8",
    )
    db = tmp_path / "omnix.db"
    store = GraphStore(str(db))
    ind.ingest_unified_codebase(str(src), store, force=True)

    edges = _calls(store)
    store.close()

    cross = [(s, t) for (s, t, sf, df) in edges if sf != df]
    assert cross, f"expected a cross-file CALLS edge, got {edges}"
    # Specifically app.main -> lib.helper
    assert any(
        s.startswith("app.py::main") and t.startswith("lib.py::helper")
        for (s, t) in cross
    ), f"expected app.main -> lib.helper, got {cross}"


def test_rust_cross_file_call_edge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from omnix.parser.grammar_detect import try_load_language_for_grammar

    if try_load_language_for_grammar("rust") is None:
        pytest.skip("tree_sitter_rust not installed")
    monkeypatch.setenv("OMNIX_INGEST_WORKERS", "1")
    src = tmp_path / "proj"
    src.mkdir()
    (src / "lib.rs").write_text("pub fn helper(x: i32) -> i32 {\n    x + 1\n}\n", encoding="utf-8")
    (src / "main.rs").write_text(
        "fn main() {\n    let _ = helper(41);\n}\n", encoding="utf-8"
    )
    db = tmp_path / "omnix.db"
    store = GraphStore(str(db))
    ind.ingest_unified_codebase(str(src), store, force=True, parse_mode="hinted")
    edges = _calls(store)
    store.close()

    cross = [
        (s, t)
        for (s, t, sf, df) in edges
        if sf != df and s.startswith("main.rs::main") and t.startswith("lib.rs::helper")
    ]
    assert cross, f"expected main.rs::main -> lib.rs::helper, got {edges}"


def test_within_file_call_still_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The global pass must not disturb correct same-file resolution."""
    monkeypatch.setenv("OMNIX_INGEST_WORKERS", "1")
    src = tmp_path / "proj"
    src.mkdir()
    (src / "solo.py").write_text(
        "def inner():\n    return 1\n\ndef outer():\n    return inner()\n",
        encoding="utf-8",
    )
    db = tmp_path / "omnix.db"
    store = GraphStore(str(db))
    ind.ingest_unified_codebase(str(src), store, force=True)
    edges = _calls(store)
    store.close()

    same = [
        (s, t)
        for (s, t, sf, df) in edges
        if sf == df and s.startswith("solo.py::outer") and t.startswith("solo.py::inner")
    ]
    assert same, f"within-file outer->inner edge missing, got {edges}"
