from __future__ import annotations

from omnix.graph.store import GraphStore
from omnix.parser.cobol.parser import ingest_cobol_to_store


def test_cst_emits_cobol_module() -> None:
    st = GraphStore(":memory:")
    ingest_cobol_to_store(st, "x.cob", "       IDENTIFICATION DIVISION.\n       PROCEDURE DIVISION.\n")
    nodes = {n.type for n in st.get_all_nodes()}
    assert "CobolModule" in nodes
    st.close()
