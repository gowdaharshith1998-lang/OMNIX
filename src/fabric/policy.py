"""src/fabric/policy.py — routing decisions and failover chain
Compliance: P12, P16, P19, P20
"""

from __future__ import annotations

from typing import Any

_VALID = frozenset({"anthropic", "openai", "google", "ollama"})


def chain_for_task(cfg: dict[str, Any], task_kind: str) -> list[str]:
    chains = cfg.get("task_chains") or {}
    if task_kind in chains and isinstance(chains[task_kind], list):
        return [str(p) for p in chains[task_kind] if str(p) in _VALID]
    return [str(p) for p in (cfg.get("default_chain") or []) if str(p) in _VALID]


def resolve_models(cfg: dict[str, Any]) -> dict[str, str]:
    dm = cfg.get("default_models") or {}
    return {k: str(dm[k]) for k in _VALID if k in dm}


def routing_decision(
    cfg: dict[str, Any],
    *,
    agent_id: str,
    task_kind: str,
    options: dict[str, Any],
    health_available: dict[str, bool],
) -> tuple[list[str], str | None, list[str]]:
    """
    Returns (provider_chain, key_source_reason, skip_reasons).
    Budget is enforced in the dispatcher, not here, so failover can try peers.
    """
    _ = agent_id
    overrides = cfg.get("agent_overrides") or {}
    if agent_id in overrides and isinstance(overrides[agent_id], dict):
        ao = overrides[agent_id]
        if isinstance(ao.get("chain"), list):
            chain = [str(p) for p in ao["chain"] if str(p) in _VALID]
        else:
            chain = chain_for_task(cfg, task_kind)
    else:
        chain = chain_for_task(cfg, task_kind)

    po = options.get("provider_override")
    if po is not None and str(po) in _VALID:
        chain = [str(po)]

    reasons: list[str] = []
    filtered: list[str] = []
    for p in chain:
        if not health_available.get(p, True):
            reasons.append(f"unhealthy:{p}")
            continue
        filtered.append(p)

    if not filtered:
        return [], "none", reasons
    return filtered, "policy", reasons


def model_for_provider(
    cfg: dict[str, Any],
    provider: str,
    options: dict[str, Any],
) -> str:
    mo = options.get("model_override")
    if mo is not None and isinstance(mo, str) and mo.strip():
        return mo.strip()
    dm = cfg.get("default_models") or {}
    return str(dm.get(provider, ""))
