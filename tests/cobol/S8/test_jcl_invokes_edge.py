from __future__ import annotations

from omnix.graph.store import GraphStore
from omnix.parser.jcl.parser import parse_jcl_text


def test_jcl_invokes_edge() -> None:
    st = GraphStore(":memory:")
    parse_jcl_text("a.jcl", "//JOB JOB\n//S1 EXEC PGM=PAYROLL\n", store=st)
    assert any(e.relationship == "invokes" for e in st.get_all_edges())
    st.close()
