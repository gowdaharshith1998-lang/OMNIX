from __future__ import annotations

from omnix.graph.store import GraphStore
from omnix.semantic.cobol.parser import parse_cobol_semantic


def test_paragraph_node() -> None:
    st = GraphStore(":memory:")
    parse_cobol_semantic(st, "x.cob", "PROCEDURE DIVISION.\nMAIN.\nSTOP RUN.\n")
    assert any(n.type == "CobolParagraph" for n in st.get_all_nodes())
    st.close()
