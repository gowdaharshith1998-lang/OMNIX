from __future__ import annotations

import asyncio
import json

from omnix.evolve.dual_evolve import FailedAttempt, co_refine
from omnix.traversal.budget import TraversalBudget
from tests.cobol.graphrag.helpers import graph, mark_enriched


class Provider:
    def complete(self, **kwargs):
        return {"content": json.dumps({"sufficient": True, "confidence": 0.9}), "cost_usd": 0.0}


def test_subgraph_result_shape(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        mark_enriched(store)
        result = asyncio.run(
            co_refine(FailedAttempt("HELLO", "spacing mismatch", "prog:HELLO"), store, Provider(), TraversalBudget())
        )
        assert result.refined_query
        assert result.new_subgraph_bundle.included
    finally:
        store.close()
