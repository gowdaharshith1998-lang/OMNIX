from __future__ import annotations

from omnix.graph.store import GraphStore
from omnix.semantic.cobol.parser import parse_cobol_semantic


def test_data_item_levels() -> None:
    st = GraphStore(":memory:")
    parse_cobol_semantic(st, "x.cob", "01 A PIC 9(2).\n77 B PIC X(3).\n")
    assert any(n.type == "CobolDataItem" for n in st.get_all_nodes())
    st.close()
