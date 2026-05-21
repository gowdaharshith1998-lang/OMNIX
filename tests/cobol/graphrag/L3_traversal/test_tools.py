from __future__ import annotations

from omnix.traversal.tools import dispatch_tool, inspect_data_item, query_graph, summarize_subgraph
from tests.cobol.graphrag.helpers import graph, mark_enriched


def test_query_graph_tool(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        assert query_graph(store, "MATCH (p)-[:call]->(q) WHERE p.name = HELLO RETURN q")
    finally:
        store.close()


def test_expand_node_tool(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        out = dispatch_tool(store, "expand_node", {"node_id": "prog:HELLO", "edge_types": ["CALLS"], "depth": 1})
        assert out[0]["node_id"] == "prog:BYE"
    finally:
        store.close()


def test_summarize_and_inspect_tools(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        mark_enriched(store)
        assert "HELLO" in summarize_subgraph(store, ["prog:HELLO"])
        assert inspect_data_item(store, "AMOUNT", "prog:HELLO")["declarations"]
    finally:
        store.close()
