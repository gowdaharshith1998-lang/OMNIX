from __future__ import annotations

from omnix.graph.store import GraphStore
from omnix.semantic.cobol.parser import parse_cobol_semantic


def test_call_static_vs_dynamic() -> None:
    st = GraphStore(":memory:")
    parse_cobol_semantic(st, "x.cob", "CALL 'PROG1'.\nCALL PROG2.\n")
    calls = [e for e in st.get_all_edges() if e.relationship == "call"]
    assert len(calls) >= 2
    st.close()
