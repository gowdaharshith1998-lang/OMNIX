from __future__ import annotations

from omnix.retrieval.graph_walker import walk_from
from tests.cobol.graphrag.helpers import graph


def test_deterministic_order_and_edge_filter(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        assert walk_from(store, "prog:HELLO", ["CALLS"]) == [("prog:BYE", 1)]
    finally:
        store.close()


def test_depth_and_node_caps(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        assert len(walk_from(store, "prog:HELLO", ["CALLS", "PERFORMS"], max_depth=1, max_nodes=1)) == 1
    finally:
        store.close()
