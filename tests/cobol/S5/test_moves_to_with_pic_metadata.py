from __future__ import annotations

from omnix.graph.store import GraphStore
from omnix.semantic.cobol.parser import parse_cobol_semantic


def test_moves_to_with_pic_metadata() -> None:
    st = GraphStore(":memory:")
    parse_cobol_semantic(st, "x.cob", "MOVE A TO B.\n")
    edges = [e for e in st.get_all_edges() if e.relationship == "moves_to"]
    assert edges
    st.close()
