"""Unknown cloud models must be costed conservatively, not as $0."""

from __future__ import annotations

from omnix.fabric import pricing


def test_known_model_uses_table():
    cost = pricing.compute_cost_usd("anthropic", "claude-sonnet-4-6", 1_000_000, 0, {})
    assert cost == 3.00


def test_unknown_model_is_not_free():
    """An un-priced cloud model previously returned $0 and silently defeated
    the daily budget cap. It must now cost the conservative fallback."""
    cost = pricing.compute_cost_usd("openai", "gpt-99-brand-new", 1_000_000, 0, {})
    assert cost > 0
    assert cost == pricing._UNKNOWN_MODEL_FALLBACK["in"]


def test_unknown_fallback_is_configurable():
    cfg = {"pricing_unknown_fallback_usd_per_million_tokens": {"in": 99.0, "out": 99.0}}
    cost = pricing.compute_cost_usd("openai", "mystery", 1_000_000, 0, cfg)
    assert cost == 99.0


def test_ollama_stays_free():
    assert pricing.compute_cost_usd("ollama", "llama3", 1_000_000, 1_000_000, {}) == 0.0
