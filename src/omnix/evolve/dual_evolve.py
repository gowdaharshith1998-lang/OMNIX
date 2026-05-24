"""Dual-evolving query/subgraph co-refinement."""

from __future__ import annotations

import re
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


BYTE_OFFSET_PATTERNS = (
    r"byte\s+offset\s+\d+",
    r"position\s+\d+\s+mismatch",
    r"trailing\s+whitespace",
    r"\bdata-item\s+padding\b",
    r"padding\s+(differs|mismatch)",
    r"fixed-width",
    r"PIC\s+[X9]\(\d+\)",
)

RECORD_TERM_PATTERNS = (
    r"record\s+terminator",
    r"line\s+ending",
    r"newline\s+mismatch",
    r"CRLF",
    r"\\r\\n",
    r"DISPLAY.*WITH\s+NO\s+ADVANCING",
)

DATA_FLOW_PATTERNS = (
    r"data\s+flow",
    r"PERFORM\s+chain",
    r"CALL\s+chain",
    r"MOVE\s+(corresponding|to)",
    r"did\s+not\s+reach",
    r"computation\s+(diverged|incorrect)",
)


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
    """
    Deterministic pre-processor for Reflexion failure text.
    Routes the refinement instruction toward the relevant subgraph slice.
    Returns a single string <= 1200 chars. Never calls an LLM.
    """
    text = (failure_analysis or "").strip()
    if not text:
        return "No prior failure analysis available; perform a broad re-traversal."

    categories = []
    if _any_match(text, BYTE_OFFSET_PATTERNS):
        categories.append("byte_offset_padding")
    if _any_match(text, RECORD_TERM_PATTERNS):
        categories.append("record_terminator")
    if _any_match(text, DATA_FLOW_PATTERNS):
        categories.append("data_flow")

    instructions = []
    if "byte_offset_padding" in categories:
        instructions.append(
            "Emphasize WORKING-STORAGE PIC clause definitions and fixed-width "
            "padding semantics. Inspect DataItem nodes."
        )
    if "record_terminator" in categories:
        instructions.append(
            "Emphasize FD / SELECT clauses, file output verbs, and DISPLAY "
            "trailing semantics. Inspect File nodes."
        )
    if "data_flow" in categories:
        instructions.append("Emphasize PERFORM / CALL / MOVE chains. Inspect ControlFlow edges.")
    if not instructions:
        return f"Refine retrieval toward this Gate 6 failure evidence: {text[:1000]}"

    return (
        "Refine retrieval based on these failure categories. "
        + " ".join(instructions)
        + f" Raw analysis excerpt: {text[:500]}"
    )[:1200]


def _any_match(text: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False
