"""src/fabric/budget.py — per-provider daily USD caps (UTC)
Compliance: P7, P16, P24
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from providers.registry import PROVIDERS

_lock = threading.Lock()
_used: dict[str, float] = {}
_day: str | None = None
_time_fn: Callable[[], float] = time.time


def set_time_fn_for_tests(fn: Callable[[], float] | None) -> None:
    global _time_fn
    _time_fn = fn or time.time


def now_unix() -> float:
    """Wall clock used for budget rollover and spend snapshots (tests may monkeypatch)."""
    return float(_time_fn())


def _utc_day(ts: float | None = None) -> str:
    t = ts if ts is not None else _time_fn()
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")


def utc_date_strings() -> tuple[str, str]:
    """Current UTC (YYYY-MM-DD, YYYY-MM) using the budget wall clock."""
    dt = datetime.fromtimestamp(_time_fn(), tz=timezone.utc)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%Y-%m")


def _rollover_if_needed() -> None:
    global _day, _used
    d = _utc_day()
    if _day != d:
        _day = d
        _used = {}


def reset_for_tests() -> None:
    global _used, _day
    with _lock:
        _used = {}
        _day = None


def used_today(provider: str) -> float:
    with _lock:
        _rollover_if_needed()
        return float(_used.get(provider, 0.0))


def cap_for_provider(cfg: dict[str, Any], provider: str) -> float:
    caps = cfg.get("budgets_usd_per_day") or {}
    return float(caps.get(provider, 0.0))


def is_exhausted(cfg: dict[str, Any], provider: str) -> bool:
    return used_today(provider) >= cap_for_provider(cfg, provider)


def budget_snapshot(cfg: dict[str, Any]) -> dict[str, dict[str, float]]:
    with _lock:
        _rollover_if_needed()
        out: dict[str, dict[str, float]] = {}
        for p in PROVIDERS:
            cap = cap_for_provider(cfg, p)
            out[p] = {"budget_used_today": float(_used.get(p, 0.0)), "budget_cap_today": cap}
        return out


def check_before_call(cfg: dict[str, Any], provider: str) -> bool:
    """Returns True if call is allowed (under cap)."""
    with _lock:
        _rollover_if_needed()
        cap = cap_for_provider(cfg, provider)
        return float(_used.get(provider, 0.0)) < cap


def commit_after_call(provider: str, cost_usd: float) -> None:
    with _lock:
        _rollover_if_needed()
        _used[provider] = float(_used.get(provider, 0.0)) + float(cost_usd)


def next_reset_utc_midnight_ts() -> float:
    """Unix timestamp of next UTC midnight (for reset_at in errors)."""
    now = datetime.fromtimestamp(_time_fn(), tz=timezone.utc)
    from datetime import timedelta

    nxt = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return nxt.timestamp()
