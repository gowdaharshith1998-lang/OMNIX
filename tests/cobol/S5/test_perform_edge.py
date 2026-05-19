from __future__ import annotations

from omnix.graph.store import GraphStore
from omnix.semantic.cobol.parser import parse_cobol_semantic


def test_perform_edge() -> None:
    st = GraphStore(":memory:")
    parse_cobol_semantic(st, "x.cob", "PROCEDURE DIVISION.\nPERFORM MAIN.\n")
    assert any(e.relationship == "perform" for e in st.get_all_edges())
    st.close()
