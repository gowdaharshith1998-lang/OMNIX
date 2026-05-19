from __future__ import annotations

from omnix.graph.store import GraphStore
from omnix.semantic.cobol.parser import parse_cobol_semantic


def test_file_io_edges() -> None:
    st = GraphStore(":memory:")
    parse_cobol_semantic(st, "x.cob", "READ INFILE.\nWRITE OUTFILE.\n")
    rels = {e.relationship for e in st.get_all_edges()}
    assert "reads_file" in rels
    assert "writes_file" in rels
    st.close()
