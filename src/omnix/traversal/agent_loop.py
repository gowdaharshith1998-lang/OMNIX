"""Observe-then-navigate traversal loop."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omnix.enrich.common import call_fabric_provider, response_content, utc_now_iso
from omnix.graph.store import GraphStore
from omnix.retrieval.token_packer import PackedBundle, estimate_tokens
from omnix.traversal.budget import TraversalBudget
from omnix.traversal.confidence import (
    ConfidenceSignal,
    parse_sufficient_signal,
    should_grant_extra_hop,
)
from omnix.traversal.tools import dispatch_tool, parse_tool_call, tool_specs_for_prompt


@dataclass(frozen=True)
class TraversalResult:
    final_bundle: PackedBundle
    traversal_path: list[dict[str, Any]]
    tokens_used: int
    sufficient_signal: ConfidenceSignal | None
    decision: str = "sufficient"
    observations: list[Any] = field(default_factory=list)


async def run_agentic_traversal(
    graph_store: GraphStore,
    target_node_id: str,
    initial_bundle: PackedBundle,
    fabric_provider: Any,
    budget: TraversalBudget,
    *,
    run_dir: Path | None = None,
    model: str = "gpt-4.1",
    confidence_threshold: float = 0.75,
    system_prompt_suffix: str = "",
) -> TraversalResult:
    observations: list[Any] = []
    path: list[dict[str, Any]] = []
    tokens_used = 0
    signal: ConfidenceSignal | None = None
    while budget.can_continue():
        prompt = _prompt(target_node_id, initial_bundle, observations, system_prompt_suffix)
        result = await call_fabric_provider(fabric_provider, prompt, model=model, json_mode=True)
        output, cost = response_content(result)
        text = output if isinstance(output, str) else json.dumps(output, sort_keys=True)
        token_cost = max(estimate_tokens(prompt + text), int(cost * 1000))
        signal = parse_sufficient_signal(text)
        if signal and signal.sufficient:
            if should_grant_extra_hop(signal, confidence_threshold) and not budget.force_after_extra_hop:
                budget.force_sufficient_after_one_more_hop()
            else:
                tokens_used += token_cost
                budget.deduct(token_cost)
                break
        tool_call = parse_tool_call(text)
        if tool_call is None:
            tokens_used += token_cost
            budget.deduct(token_cost)
            signal = ConfidenceSignal(False, 0.0)
            continue
        tool_name, args = tool_call
        observation = dispatch_tool(graph_store, tool_name, args)
        observations.append(observation)
        if tool_name == "expand_node":
            budget.note_hop(int(args.get("depth", 1)))
        event = {
            "timestamp": utc_now_iso(),
            "turn_index": len(path),
            "tool_name": tool_name,
            "args": args,
            "result_summary": _summarize_observation(observation),
            "tokens_consumed": token_cost,
        }
        path.append(event)
        _write_log(run_dir, target_node_id, event)
        tokens_used += token_cost
        budget.deduct(token_cost)
        if budget.force_after_extra_hop:
            signal = ConfidenceSignal(True, confidence_threshold)
            break
    decision = "sufficient" if signal and signal.sufficient else "InsufficientContext"
    return TraversalResult(initial_bundle, path, tokens_used, signal, decision, observations)


def _prompt(
    target_node_id: str,
    initial_bundle: PackedBundle,
    observations: list[Any],
    suffix: str,
) -> str:
    return json.dumps(
        {
            "instruction": "Observe available graph context, then call one tool or emit {'sufficient': true, 'confidence': float}.",
            "target_node_id": target_node_id,
            "tools": tool_specs_for_prompt(),
            "initial_context": initial_bundle.content,
            "observations": observations,
            "refinement": suffix,
        },
        sort_keys=True,
    )


def _summarize_observation(observation: Any) -> str:
    text = json.dumps(observation, sort_keys=True, default=str)
    return text[:500]


def _write_log(run_dir: Path | None, program_id: str, event: dict[str, Any]) -> None:
    if run_dir is None:
        return
    path = run_dir / "traversal" / f"{program_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")
