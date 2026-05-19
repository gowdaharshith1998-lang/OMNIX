from __future__ import annotations

from omnix.graph.store import GraphStore
from omnix.semantic.cobol.parser import parse_cobol_semantic


def test_division_decomposition() -> None:
    st = GraphStore(":memory:")
    parse_cobol_semantic(st, "x.cob", "IDENTIFICATION DIVISION.\nDATA DIVISION.\nPROCEDURE DIVISION.\n")
    assert sum(1 for n in st.get_all_nodes() if n.type == "CobolDivision") >= 2
    st.close()
