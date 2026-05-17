"""Graph store iterators, scoped queries, and index presence."""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Generator

from omnix.graph.store import EdgeRow, GraphStore, NodeRow
from omnix.parser.memory_graph import MemoryGraphStore


def _tmp_store() -> GraphStore:
    t = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    t.close()
    return GraphStore(t.name)


def test_iter_all_nodes_yields_same_as_get_all_nodes() -> None:
    store = _tmp_store()
    for i, fp in enumerate(("a.py", "b.py", "c.py")):
        store.add_node(
            id=f"{fp}::f",
            name="f",
            type="function",
            file_path=fp,
        )
    store.commit()
    assert [n.id for n in store.iter_all_nodes()] == [n.id for n in store.get_all_nodes()]


def test_iter_all_edges_yields_same_as_get_all_edges() -> None:
    store = _tmp_store()
    for fp in ("a.py", "b.py", "c.py"):
        store.add_node(
            id=f"{fp}::f",
            name="f",
            type="function",
            file_path=fp,
        )
    store.add_edge("a.py::f", "b.py::f", "CALLS")
    store.add_edge("b.py::f", "c.py::f", "CALLS")
    store.add_edge("c.py::f", "a.py::f", "REF", None)
    store.commit()
    got = [(e.source_id, e.target_id, e.relationship) for e in store.iter_all_edges()]
    from_get = [
        (e.source_id, e.target_id, e.relationship) for e in store.get_all_edges()
    ]
    assert sorted(got) == sorted(from_get)


def test_count_edges_matches_iter_count() -> None:
    store = _tmp_store()
    store.add_node("m.py::m", "m", "function", "m.py")
    for i in range(100):
        tid = f"t{i}.py::f"
        store.add_node(tid, "f", "function", f"t{i}.py")
        store.add_edge("m.py::m", tid, "X")
    store.commit()
    n_iter = sum(1 for _ in store.iter_all_edges())
    assert store.count_edges() == store.edge_count() == n_iter == 100


def test_iter_streams_without_materialization() -> None:
    store = _tmp_store()
    store.add_node("a.py::f", "f", "function", "a.py")
    for i in range(200):
        store.add_edge("a.py::f", f"t{i}::f", "CALLS")
    store.commit()
    it: Generator[EdgeRow, None, None] = store.iter_all_edges()
    elist = store.get_all_edges()
    # Iterator object is small; full list of EdgeRow holds row payloads.
    assert sys.getsizeof(it) < sys.getsizeof(elist)


def test_iter_nodes_by_file_returns_only_matching_file() -> None:
    store = _tmp_store()
    store.add_node("a.py::1", "a1", "function", "a.py")
    store.add_node("a.py::2", "a2", "class", "a.py")
    store.add_node("b.py::1", "b1", "function", "b.py")
    store.commit()
    a_only = {n.id for n in store.iter_nodes_by_file("a.py")}
    assert a_only == {"a.py::1", "a.py::2"}


def test_count_call_edges_for_file_matches_python_filter() -> None:
    store = _tmp_store()
    store.add_node("a.py::f", "f", "function", "a.py")
    store.add_node("a.py::inner::g", "g", "function", "a.py")
    store.add_node("a.py.extra::g", "g", "function", "a.py.extra")
    store.add_node("b.py::f", "f", "function", "b.py")
    store.add_node("x", "x", "function", "x.py")
    store.add_node("y", "y", "function", "y.py")
    store.add_node("z", "z", "function", "z.py")
    store.add_node("z2", "z2", "function", "z2.py")
    store.add_node("z3", "z3", "function", "z3.py")
    for s, t, r in [
        ("a.py::f", "x", "CALLS"),
        ("a.py::f", "y", "REF"),
        ("a.py::inner::g", "z", "CALLS"),
        ("a.py.extra::g", "z2", "CALLS"),
        ("b.py::f", "z3", "CALLS"),
    ]:
        store.add_edge(s, t, r, None)
    store.commit()
    by_py = sum(
        1
        for e in store.get_all_edges()
        if e.source_id.startswith("a.py") and e.relationship == "CALLS"
    )
    assert store.count_call_edges_for_file("a.py") == by_py


def test_memory_graph_parity() -> None:
    m = MemoryGraphStore()
    m.add_node("a.py::f", "f", "function", "a.py")
    m.add_node("a.py::x", "x", "function", "a.py")
    m.add_node("b.py::f", "f", "function", "b.py")
    m.add_edge("a.py::f", "b.py::f", "CALLS", None)
    m.add_edge("a.py::x", "b.py::f", "REF", None)
    all_e = m.get_all_edges()
    by_hand = sum(
        1
        for e in all_e
        if e.source_id.startswith("a.py") and e.relationship == "CALLS"
    )
    assert m.count_call_edges_for_file("a.py") == by_hand


def test_indexes_exist_in_schema() -> None:
    store = _tmp_store()
    con = store.sqlite_connection()
    rows = con.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
    names = {r[0] for r in rows if r[0] is not None}
    assert "idx_nodes_file_path" in names
    assert "idx_edges_source_id" in names
    assert "idx_edges_source_rel" in names
    assert "idx_edges_source" not in names
