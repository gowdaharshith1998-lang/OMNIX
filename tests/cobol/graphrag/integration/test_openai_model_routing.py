from __future__ import annotations

from typing import Any

from omnix.enrich.live_provider import OpenAIEnrichmentProvider, route_enrichment_model


def test_anthropic_named_enrichment_models_route_to_openai_equivalents() -> None:
    assert route_enrichment_model("claude-haiku-4.5") == "gpt-4.1-mini"
    assert route_enrichment_model("claude-sonnet-4.6") == "gpt-4.1"
    assert route_enrichment_model("claude-opus-4.7") == "gpt-4.1"
    assert route_enrichment_model("gpt-5") == "gpt-5"


def test_live_enrichment_provider_forces_openai_dispatch(monkeypatch: Any) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen: dict[str, Any] = {}

    def fake_dispatch(payload: dict[str, Any]) -> dict[str, Any]:
        seen.update(payload)
        return {"ok": True, "content": "{}", "provider": "openai", "model": "gpt-4.1"}

    monkeypatch.setattr("omnix.enrich.live_provider.fabric_dispatch", fake_dispatch)

    out = OpenAIEnrichmentProvider().complete(prompt="{}", model="claude-opus-4.7")

    assert out["ok"] is True
    assert seen["provider_key"]["provider"] == "openai"
    assert seen["options"]["provider_override"] == "openai"
    assert seen["options"]["model_override"] == "gpt-4.1"
