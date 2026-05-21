"""Dual-evolving query/subgraph co-refinement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from omnix.graph.store import GraphStore
from omnix.retrieval.hybrid import retrieve
from omnix.traversal.agent_loop import run_agentic_traversal
from omnix.traversal.budget import TraversalBudget


@dataclass(frozen=True)
class FailedAttempt:
    program_id: str
    failure_analysis: str
    target_node_id: str


@dataclass(frozen=True)
class CoRefinementResult:
    refined_query: str
    new_subgraph_bundle: Any
    tokens_used: int
    has_new_evidence: bool


async def co_refine(
    failed_attempt: FailedAttempt,
    graph_store: GraphStore,
    fabric_provider: Any,
    original_budget: TraversalBudget,
) -> CoRefinementResult:
    if original_budget.tokens_remaining <= 0:
        bundle = retrieve(graph_store, failed_attempt.target_node_id, budget_tokens=1)
        return CoRefinementResult("", bundle, 0, False)
    refined_query = parse_failure_analysis(failed_attempt.failure_analysis)
    bundle = retrieve(
        graph_store,
        failed_attempt.target_node_id,
        budget_tokens=max(1, original_budget.tokens_remaining),
    )
    before = set(bundle.node_ids)
    traversal = await run_agentic_traversal(
        graph_store,
        failed_attempt.target_node_id,
        bundle,
        fabric_provider,
        original_budget,
        system_prompt_suffix=refined_query,
    )
    after = set(getattr(traversal.final_bundle, "node_ids", []) or [])
    return CoRefinementResult(refined_query, traversal.final_bundle, traversal.tokens_used, before != after)


def parse_failure_analysis(failure_analysis: str) -> str:
    text = failure_analysis.strip()
    if not text:
        return "Focus on byte-level Gate 6 mismatch evidence."
    return "Refine retrieval toward this Gate 6 failure evidence: " + text[:1000]
