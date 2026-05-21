"""Deterministic fixture provider used by offline GraphRAG tests and CLI dry runs."""

from __future__ import annotations

import json
import re
from typing import Any


class MockEnrichmentProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def complete(self, *, prompt: str, model: str, json_mode: bool = True, **_: Any) -> dict[str, Any]:
        self.calls.append({"prompt": prompt, "model": model, "json_mode": json_mode})
        if "signature_summary" in prompt:
            payload = _node_ids(prompt)
            return {"content": json.dumps({node_id: _signature(node_id) for node_id in payload}), "cost_usd": 0.001}
        if "logic_summary" in prompt:
            node_id = _first_node_id(prompt)
            return {
                "content": json.dumps(
                    {
                        node_id: {
                            "logic_summary": f"{node_id} applies deterministic COBOL control flow.",
                            "business_rules": ["Preserve externally observable output bytes."],
                        }
                    }
                ),
                "cost_usd": 0.002,
            }
        if "data_flow_summary" in prompt:
            node_id = _first_node_id(prompt)
            return {
                "content": json.dumps(
                    {
                        node_id: {
                            "data_flow_summary": f"{node_id} reads fixture input and emits captured output.",
                            "copybooks_resolved": [],
                            "jcl_context": [],
                        }
                    }
                ),
                "cost_usd": 0.003,
            }
        if "community_summary" in prompt:
            return {"content": json.dumps({"community_summary": "COBOL subsystem community."}), "cost_usd": 0.003}
        if "'skills'" in prompt or '"skills"' in prompt:
            return {
                "content": json.dumps(
                    {
                        "skills": [
                            {
                                "title": "Preserve byte-exact record formatting",
                                "description": "Use fixture byte diffs to preserve newlines and fixed-width spacing.",
                                "match_predicate": {"contains": "COBOL"},
                                "prompt_addendum": "Pay special attention to fixed-width padding and record terminators.",
                            }
                        ]
                    }
                ),
                "cost_usd": 0.01,
            }
        return {"content": json.dumps({"sufficient": True, "confidence": 0.9}), "cost_usd": 0.001}


def _node_ids(prompt: str) -> list[str]:
    try:
        payload = json.loads(prompt[prompt.index("[") :])
        if isinstance(payload, list):
            return [str(item.get("node_id") or item.get("name") or "node") for item in payload]
    except (ValueError, json.JSONDecodeError):
        pass
    found = re.findall(r'"node_id"\s*:\s*"([^"]+)"', prompt)
    return found or ["node"]


def _first_node_id(prompt: str) -> str:
    found = _node_ids(prompt)
    return found[0] if found else "node"


def _signature(node_id: str) -> dict[str, Any]:
    return {
        "signature_summary": f"{node_id} COBOL behavior signature.",
        "signature_inputs": ["stdin"],
        "signature_outputs": ["stdout"],
    }
