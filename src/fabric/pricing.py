"""src/fabric/pricing.py — default price table + cost computation
Compliance: P16, P24
"""

from __future__ import annotations

from typing import Any

# Defaults only; merged from fabric_config.json at runtime (P16).
_DEFAULT_PRICING: dict[str, dict[str, float]] = {
    "anthropic:claude-haiku-4-5": {"in": 0.80, "out": 4.00},
    "anthropic:claude-sonnet-4-6": {"in": 3.00, "out": 15.00},
    "anthropic:claude-opus-4-7": {"in": 15.00, "out": 75.00},
    "openai:gpt-5": {"in": 5.00, "out": 20.00},
    "openai:gpt-4.1": {"in": 2.00, "out": 8.00},
    "openai:gpt-4.1-mini": {"in": 0.40, "out": 1.60},
    "google:gemini-2.5-pro": {"in": 1.25, "out": 10.00},
    "google:gemini-2.5-flash": {"in": 0.075, "out": 0.30},
}


def merged_pricing_table(cfg: dict[str, Any]) -> dict[str, dict[str, float]]:
    raw = cfg.get("pricing_usd_per_million_tokens") or {}
    out: dict[str, dict[str, float]] = {**_DEFAULT_PRICING}
    for k, v in raw.items():
        if isinstance(v, dict) and "in" in v and "out" in v:
            out[str(k)] = {"in": float(v["in"]), "out": float(v["out"])}
    return out


def compute_cost_usd(
    provider: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cfg: dict[str, Any],
) -> float:
    if provider == "ollama":
        return 0.0
    key = f"{provider}:{model}"
    table = merged_pricing_table(cfg)
    row = table.get(key) or table.get(
        f"{provider}:{model}",
        {"in": 0.0, "out": 0.0},
    )
    cost = (tokens_in / 1_000_000.0) * row["in"] + (
        tokens_out / 1_000_000.0
    ) * row["out"]
    return round(cost, 6)
