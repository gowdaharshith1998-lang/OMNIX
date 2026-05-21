from __future__ import annotations

import asyncio
import json

from omnix.retrieval.hybrid import retrieve
from omnix.traversal.agent_loop import run_agentic_traversal
from omnix.traversal.budget import TraversalBudget
from tests.cobol.graphrag.helpers import graph, mark_enriched


class ScriptedProvider:
    def __init__(self, outputs):
        self.outputs = list(outputs)

    def complete(self, **kwargs):
        return {"content": self.outputs.pop(0), "cost_usd": 0.0}


def test_agent_loop_trajectory_exits_sufficient(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        mark_enriched(store)
        bundle = retrieve(store, "prog:HELLO")
        provider = ScriptedProvider(
            [
                json.dumps({"tool": "expand_node", "args": {"node_id": "prog:HELLO", "edge_types": ["CALLS"], "depth": 1}}),
                json.dumps({"sufficient": True, "confidence": 0.9}),
            ]
        )
        result = asyncio.run(
            run_agentic_traversal(store, "prog:HELLO", bundle, provider, TraversalBudget(), run_dir=tmp_path)
        )
        assert result.decision == "sufficient"
        assert (tmp_path / "traversal" / "prog:HELLO.jsonl").is_file()
    finally:
        store.close()
