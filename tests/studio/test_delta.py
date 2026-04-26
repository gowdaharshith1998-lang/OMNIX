"""Unit tests for :func:`src.studio.delta.compute_file_delta`."""

from __future__ import annotations

from src.graph.store import EdgeRow, NodeRow
from src.studio.delta import compute_file_delta


def _n(  # noqa: D103
    id: str, name: str, type: str, fp: str, sl: int = 1, el: int = 1
) -> NodeRow:  # noqa: N802, E501, E501, E501
    return NodeRow(
        id=id,
        name=name,
        type=type,
        file_path=fp,
        start_line=sl,
        end_line=el,
        complexity=0,
        metadata={},
    )


def _e(  # noqa: D103
    eid: int, a: str, b: str, r: str = "CALLS"
) -> EdgeRow:  # noqa: E501, E501, E501, E501, E501
    return EdgeRow(
        id=eid, source_id=a, target_id=b, relationship=r, metadata=None
    )


def test_delta_detects_added_node() -> None:  # noqa: D103
    n = _n("a1", "f", "function", "a.py", 1, 2)  # noqa: E501
    d = compute_file_delta("a.py", [], [n], [], [])
    assert {x.id for x in d["added_nodes"]} == {"a1"}  # type: ignore[no-untyped-def, misc, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
    assert not d.get("removed_node_ids")  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501


def test_delta_detects_removed_node() -> None:  # noqa: D103
    n = _n("a1", "f", "function", "a.py", 1, 2)  # noqa: E501
    d = compute_file_delta("a.py", [n], [], [], [])
    assert d["removed_node_ids"] == ["a1"]  # type: ignore[no-untyped-def, misc, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501


def test_delta_detects_modified_node() -> None:  # noqa: D103
    o = _n("a1", "f", "function", "a.py", 1, 2)  # noqa: E501
    n2 = _n("a1", "f2", "function", "a.py", 1, 3)  # noqa: E501
    d = compute_file_delta("a.py", [o], [n2], [], [])
    ch = d.get("node_modified")  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
    assert ch and ch[0]["node_id"] == "a1"  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501


def test_delta_detects_added_edge() -> None:  # noqa: D103
    n1, n2 = (  # noqa: E501
        _n("a1", "f", "function", "a.py"),  # noqa: E501
        _n("a2", "b", "function", "a.py"),  # noqa: E501
    )
    e0 = _e(1, "a1", "a2", "CALLS")
    d = compute_file_delta(  # noqa: E501
        "a.py",  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
        [n1, n2],  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
        [n1, n2],  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
        [],  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
        [e0],  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
    )
    assert d["added_edges"]  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501


def test_delta_no_change_returns_empty() -> None:  # noqa: D103
    n1 = _n("a1", "f", "function", "a.py")
    e0 = _e(1, "a1", "a2", "IMP")  # noqa: E501
    d = compute_file_delta(  # noqa: E501
        "a.py", [n1], [n1], [e0], [e0]  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
    )
    assert (  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
        not d["added_nodes"]  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
    )
    assert not d["added_edges"]  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
