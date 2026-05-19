from __future__ import annotations

from omnix.graph.store import GraphStore
from omnix.parser.ingest_dispatch import ingest_one_path


def test_module_node_persist(tmp_path) -> None:
    f = tmp_path / "payroll.cob"
    f.write_text("       IDENTIFICATION DIVISION.\n       PROCEDURE DIVISION.\n", encoding="utf-8")
    st = GraphStore(":memory:")
    status, grammar = ingest_one_path(st, tmp_path, f)
    assert status is None
    assert grammar == "cobol"
    assert any(n.type == "CobolModule" for n in st.get_all_nodes())
    st.close()
