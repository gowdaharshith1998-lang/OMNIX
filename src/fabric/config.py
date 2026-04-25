"""src/fabric/config.py — fabric_config.json load/save
Compliance: P16, P20
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

CONFIG_PATH = Path.home() / ".omnix" / "fabric_config.json"

_DEFAULT: dict[str, Any] = {
    "default_chain": ["anthropic", "openai", "google", "ollama"],
    "task_chains": {
        "code_review": ["anthropic"],
        "debug": ["anthropic", "openai"],
        "architecture": ["anthropic", "openai"],
        "parse_extract": ["ollama", "openai", "google", "anthropic"],
        "fuzz_inputs": ["ollama", "openai", "google", "anthropic"],
        "code_fix": ["ollama", "openai", "google", "anthropic"],
    },
    "agent_overrides": {},
    "budgets_usd_per_day": {
        "anthropic": 20.0,
        "openai": 20.0,
        "google": 20.0,
        "ollama": 1000000.0,
    },
    "default_models": {
        "anthropic": "claude-haiku-4-5",
        "openai": "gpt-4.1-mini",
        "google": "gemini-2.5-flash",
        "ollama": "llama3.2:3b",
    },
    "pricing_usd_per_million_tokens": {
        "anthropic:claude-haiku-4-5": {"in": 0.80, "out": 4.00},
        "anthropic:claude-sonnet-4-6": {"in": 3.00, "out": 15.00},
        "openai:gpt-4.1-mini": {"in": 0.40, "out": 1.60},
        "google:gemini-2.5-flash": {"in": 0.075, "out": 0.30},
    },
    "ollama_base_url": "http://127.0.0.1:11434",
    "n_max_attempts_default": 3,
    "max_concurrent_dispatches": 4,
}


def default_config() -> dict[str, Any]:
    return deepcopy(_DEFAULT)


def load_config(path: Path | None = None) -> dict[str, Any]:
    p = path or CONFIG_PATH
    if not p.is_file():
        cfg = default_config()
        save_config(cfg, p)
        return deepcopy(cfg)
    raw = p.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        return default_config()
    merged = default_config()
    merged.update(data)
    if "task_chains" in data and isinstance(data["task_chains"], dict):
        merged["task_chains"] = {**merged["task_chains"], **data["task_chains"]}
    if "pricing_usd_per_million_tokens" in data and isinstance(
        data["pricing_usd_per_million_tokens"], dict
    ):
        merged["pricing_usd_per_million_tokens"] = {
            **merged["pricing_usd_per_million_tokens"],
            **data["pricing_usd_per_million_tokens"],
        }
    return merged


def save_config(cfg: dict[str, Any], path: Path | None = None) -> None:
    p = path or CONFIG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(cfg, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
