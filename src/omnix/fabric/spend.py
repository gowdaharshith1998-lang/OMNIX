"""src/fabric/spend.py — aggregate spend view from telemetry + budget
Compliance: P11, P12, P16, P24
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from omnix.fabric import budget, telemetry

_PROVIDERS = ("anthropic", "openai", "google", "ollama")


def _iso_computed_at(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def _entry_day(entry: dict[str, Any]) -> str | None:
    t = entry.get("completed_at") or entry.get("started_at")
    if isinstance(t, str) and len(t) >= 10:
        return t[:10]
    return None


def _entry_month(entry: dict[str, Any]) -> str | None:
    d = _entry_day(entry)
    return d[:7] if d else None


def spend_snapshot(cfg: dict[str, Any]) -> dict[str, Any]:
    """
    Aggregate on-demand from the in-memory telemetry ring and budget tracker.
    Month figures include only rows still present in the buffer (max 1000).
    """
    now_ts = budget.now_unix()
    today_d, month_m = budget.utc_date_strings()
    computed_at = _iso_computed_at(now_ts)

    items = telemetry.recent()
    by_provider: dict[str, dict[str, Any]] = {}

    for p in _PROVIDERS:
        cap = budget.cap_for_provider(cfg, p)
        used = budget.used_today(p)
        remaining = round(max(0.0, float(cap) - float(used)), 6)

        today_rows = [
            e
            for e in items
            if e.get("provider") == p and _entry_day(e) == today_d
        ]
        month_rows = [
            e
            for e in items
            if e.get("provider") == p and _entry_month(e) == month_m
        ]

        today_calls = len(today_rows)
        month_calls = len(month_rows)

        def _tok_sum(rows: list[dict[str, Any]], k: str) -> int:
            s = 0
            for e in rows:
                if e.get("status") != "ok":
                    continue
                v = e.get(k)
                if v is None:
                    continue
                try:
                    s += int(v)
                except (TypeError, ValueError):
                    pass
            return s

        today_tokens_in = _tok_sum(today_rows, "tokens_in")
        today_tokens_out = _tok_sum(today_rows, "tokens_out")

        month_usd = round(
            sum(
                float(e.get("cost_usd", 0) or 0)
                for e in month_rows
                if e.get("status") == "ok"
            ),
            6,
        )

        last_ts: str | None = None
        for e in items:
            if e.get("provider") != p:
                continue
            c = e.get("completed_at")
            if isinstance(c, str) and (last_ts is None or c > last_ts):
                last_ts = c

        by_provider[p] = {
            "today_usd": round(float(used), 6),
            "today_calls": today_calls,
            "today_tokens_in": today_tokens_in,
            "today_tokens_out": today_tokens_out,
            "month_usd": month_usd,
            "month_calls": month_calls,
            "last_call_at": last_ts,
            "budget_cap_today_usd": round(float(cap), 6),
            "budget_remaining_today_usd": remaining,
        }

    totals_today_usd = round(
        sum(float(by_provider[p]["today_usd"]) for p in _PROVIDERS), 6
    )
    totals_today_calls = sum(int(by_provider[p]["today_calls"]) for p in _PROVIDERS)
    totals_month_usd = round(
        sum(float(by_provider[p]["month_usd"]) for p in _PROVIDERS), 6
    )

    return {
        "by_provider": by_provider,
        "totals": {
            "today_usd": totals_today_usd,
            "today_calls": totals_today_calls,
            "month_usd": totals_month_usd,
        },
        "computed_at": computed_at,
    }
