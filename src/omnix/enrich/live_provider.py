"""Live enrichment provider backed by the existing OpenAI-compatible fabric."""

from __future__ import annotations

import os
from typing import Any

from omnix.fabric.dispatcher import dispatch as fabric_dispatch
from omnix.providers.registry import PROVIDERS

OPENAI_FAST_MODEL = "gpt-4.1-mini"
OPENAI_STRONG_MODEL = "gpt-4.1"


def route_enrichment_model(model: str | None) -> str:
    """Map legacy Anthropic enrichment tiers to OpenAI-compatible models."""
    requested = (model or "").strip()
    lowered = requested.lower()
    if "haiku" in lowered:
        return os.environ.get("OMNIX_GRAPHRAG_OPENAI_FAST_MODEL", OPENAI_FAST_MODEL)
    if lowered.startswith("anthropic/") or "sonnet" in lowered or "opus" in lowered:
        return os.environ.get("OMNIX_GRAPHRAG_OPENAI_STRONG_MODEL", OPENAI_STRONG_MODEL)
    if lowered.startswith("openai/"):
        return requested.split("/", 1)[1]
    if lowered.startswith(("gpt-", "o1", "o3", "o4")):
        return requested
    return PROVIDERS["openai"].default_model or "gpt-4o"


class OpenAIEnrichmentProvider:
    """Adapter exposing the provider interface used by GraphRAG enrichment."""

    def __init__(self, *, api_key: str | None = None, timeout_ms: int = 120_000, max_tokens: int = 4096) -> None:
        self.api_key = api_key
        self.timeout_ms = timeout_ms
        self.max_tokens = max_tokens

    def complete(
        self,
        *,
        prompt: str,
        model: str,
        json_mode: bool = True,
        system_prompt: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        key = self.api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("OMNIX_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY or OMNIX_API_KEY is required for live COBOL GraphRAG enrichment")
        routed_model = route_enrichment_model(model)
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "agent_id": "omnix-cobol-graphrag-enrich",
            "task_kind": "cobol_graphrag_enrich",
            "provider_key": {"provider": "openai", "key": key},
            "options": {
                "provider_override": "openai",
                "model_override": routed_model,
                "timeout_ms": self.timeout_ms,
                "max_tokens": self.max_tokens,
                "response_format": "json_object" if json_mode else None,
            },
            "messages": messages,
        }
        out = fabric_dispatch(payload)
        if not isinstance(out, dict) or not out.get("ok"):
            err = out.get("error", "unknown") if isinstance(out, dict) else "invalid_response"
            raise RuntimeError(f"OpenAI enrichment dispatch failed: {err}")
        return out
