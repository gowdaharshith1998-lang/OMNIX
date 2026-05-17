"""src/fabric/dispatcher.py — main dispatch entrypoint
Compliance: P11, P12, P13, P14, P17, P18, P19, P24
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
import urllib.error
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omnix.fabric import budget, dedup, health, policy, pricing, receipts, telemetry
from omnix.fabric.config import load_config
from omnix.fabric.providers import anthropic, google, ollama, openai_compatible
from omnix.fabric.providers.common import is_transient_http_status
from omnix.providers.registry import PROVIDERS, valid_provider_names

_LOG = logging.getLogger("omnix.fabric")

_VALID = valid_provider_names()
_inflight_lock = threading.Lock()
_inflight_by_provider: dict[str, int] = defaultdict(int)


def reset_runtime_for_tests() -> None:
    global _inflight_by_provider
    with _inflight_lock:
        _inflight_by_provider = defaultdict(int)
    budget.reset_for_tests()
    dedup.reset_for_tests()
    health.reset_for_tests()
    telemetry.reset_for_tests()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def _inc_flight(provider: str) -> None:
    with _inflight_lock:
        _inflight_by_provider[provider] += 1


def _dec_flight(provider: str) -> None:
    with _inflight_lock:
        _inflight_by_provider[provider] = max(
            0, _inflight_by_provider[provider] - 1
        )


def inflight_for_provider(provider: str) -> int:
    with _inflight_lock:
        return int(_inflight_by_provider.get(provider, 0))


def _validate_payload(data: dict[str, Any]) -> None:
    pk = data.get("provider_key")
    if not isinstance(pk, dict):
        raise ValueError("provider_key must be an object")
    pr = pk.get("provider")
    ky = pk.get("key")
    if pr not in _VALID:
        raise ValueError("invalid provider_key.provider")
    if not isinstance(ky, str) or len(ky) > 512:
        raise ValueError("invalid provider_key.key")
    extra = data.get("provider_keys")
    if extra is not None:
        if not isinstance(extra, dict):
            raise ValueError("provider_keys must be an object")
        for k, v in extra.items():
            if k not in _VALID:
                raise ValueError("invalid provider_keys key")
            if not isinstance(v, str) or len(v) > 512:
                raise ValueError("invalid provider_keys value")


def _merge_keys(data: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    extra = data.get("provider_keys")
    if isinstance(extra, dict):
        for k, v in extra.items():
            if k in _VALID and isinstance(v, str) and len(v) <= 512:
                out[str(k)] = v
    pk = data.get("provider_key")
    if isinstance(pk, dict):
        p = str(pk.get("provider"))
        k = pk.get("key")
        if p in _VALID and isinstance(k, str) and len(k) <= 512:
            out[p] = k
    return out


def _normalize_messages(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role", "user"))
        if role not in ("user", "assistant", "system"):
            role = "user"
        out.append({"role": role, "content": str(m.get("content", ""))})
    return out


def _call_provider(
    provider: str,
    model: str,
    key: str,
    messages: list[dict[str, str]],
    options: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    timeout_ms = int(options.get("timeout_ms", 30000))
    timeout_s = max(1.0, timeout_ms / 1000.0)
    max_tokens = int(options.get("max_tokens", 4096))
    if provider == "anthropic":
        st, data = anthropic.call(
            model=model,
            api_key=key,
            messages=messages,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
        return anthropic.normalize_response(st, data)
    spec = PROVIDERS.get(provider)
    if spec and spec.adapter == "openai_compatible":
        base_url = spec.base_url
        if provider == "custom":
            custom_base = options.get("custom_base_url")
            if isinstance(custom_base, str) and custom_base.strip():
                base_url = custom_base.strip()
        st, data = openai_compatible.call(
            model=model,
            api_key=key,
            messages=messages,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
            base_url=base_url,
            chat_endpoint=spec.chat_endpoint,
        )
        return openai_compatible.normalize_response(st, data)
    if spec and spec.adapter == "google":
        st, data = google.call(
            model=model,
            api_key=key,
            messages=messages,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
        return google.normalize_response(st, data)
    if spec and spec.adapter == "ollama":
        base = str(spec.base_url or cfg.get("ollama_base_url") or "http://127.0.0.1:11434")
        st, data = ollama.call(
            model=model,
            api_key=key,
            base_url=base,
            messages=messages,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
        return ollama.normalize_response(st, data)
    raise ValueError("unknown provider")


def _n_max_for_task(cfg: dict[str, Any], task_kind: str) -> int:
    by_task = cfg.get("n_max_attempts_by_task") or {}
    if task_kind in by_task:
        return int(by_task[task_kind])
    return int(cfg.get("n_max_attempts_default", 3))


def dispatch(
    data: dict[str, Any],
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    _validate_payload(data)
    agent_id = str(data.get("agent_id", ""))
    task_kind = str(data.get("task_kind", "default"))
    messages = _normalize_messages(data.get("messages"))
    options = data.get("options") if isinstance(data.get("options"), dict) else {}
    options = dict(options)
    call_id = secrets.token_hex(16)
    idem = options.get("idempotency_key")
    if isinstance(idem, str) and idem:
        dup, fut = dedup.acquire(agent_id, idem)
        if dup:
            try:
                out = fut.result(timeout=int(options.get("timeout_ms", 30000)) / 1000.0 + 60.0)
            except Exception:
                raise
            if isinstance(out, dict):
                out = dict(out)
                out["deduped"] = True
            cid = out.get("call_id", call_id) if isinstance(out, dict) else call_id
            telemetry.record(
                {
                    "call_id": cid,
                    "agent_id": agent_id,
                    "provider": out.get("provider") if isinstance(out, dict) else None,
                    "model": out.get("model") if isinstance(out, dict) else None,
                    "latency_ms": 0,
                    "tokens_in": (out.get("usage") or {}).get("tokens_in")
                    if isinstance(out, dict)
                    else None,
                    "tokens_out": (out.get("usage") or {}).get("tokens_out")
                    if isinstance(out, dict)
                    else None,
                    "cost_usd": 0.0,
                    "status": "deduped",
                    "error_code_if_any": None,
                    "started_at": _iso(time.time()),
                    "completed_at": _iso(time.time()),
                    "deduped": True,
                }
            )
            return out
        leader_future = fut
    else:
        leader_future = None

    keys_map = _merge_keys(data)
    cfg = load_config(config_path)

    health_map = {p: health.is_available(p) for p in _VALID}
    chain, _reason, _skip = policy.routing_decision(
        cfg,
        agent_id=agent_id,
        task_kind=task_kind,
        options=options,
        health_available=health_map,
    )

    n_max = _n_max_for_task(cfg, task_kind)
    started = time.time()
    failover_log: list[dict[str, str]] = []
    last_error: str | None = None
    last_http: int | None = None
    receipt_path: str | None = None
    http_tried = False
    saw_budget_skip = False

    def _finish_receipt(
        *,
        event: str,
        provider: str | None,
        model: str | None,
        status: str,
        latency_ms: int,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        error_code: str | None,
        content_ok: bool,
    ) -> str:
        rec = {
            "event": event,
            "call_id": call_id,
            "agent_id": agent_id,
            "task_kind": task_kind,
            "provider": provider,
            "model": model,
            "latency_ms": latency_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": round(float(cost_usd), 6),
            "status": status,
            "error_code": error_code,
            "started_at": _iso(started),
            "completed_at": _iso(time.time()),
            "failover_events": failover_log,
            "content_returned": bool(content_ok),
        }
        return receipts.write_call_receipt(rec)

    try:
        if not chain:
            completed = time.time()
            latency_ms = int((completed - started) * 1000)
            receipt_path = _finish_receipt(
                event="call.refused",
                provider=None,
                model=None,
                status="error",
                latency_ms=latency_ms,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                error_code="no_route",
                content_ok=False,
            )
            out = {
                "ok": False,
                "error": "no_route",
                "call_id": call_id,
                "receipt_path": receipt_path,
            }
            telemetry.record(
                {
                    "call_id": call_id,
                    "agent_id": agent_id,
                    "provider": None,
                    "model": None,
                    "latency_ms": latency_ms,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "cost_usd": 0.0,
                    "status": "error",
                    "error_code_if_any": "no_route",
                    "started_at": _iso(started),
                    "completed_at": _iso(completed),
                }
            )
            _LOG.info(
                "fabric call_id=%s agent_id=%s provider=%s model=%s "
                "latency_ms=%s status=%s",
                call_id,
                agent_id,
                None,
                None,
                latency_ms,
                "error",
            )
            if leader_future is not None and isinstance(idem, str):
                dedup.complete(agent_id, idem, out)
            return out

        prev_provider: str | None = None
        for provider in chain:
            model = policy.model_for_provider(cfg, provider, options)
            if not model:
                last_error = "no_model"
                continue

            if not budget.check_before_call(cfg, provider):
                saw_budget_skip = True
                last_error = "budget_exhausted"
                idx = chain.index(provider)
                nxt = chain[idx + 1] if idx + 1 < len(chain) else None
                if nxt is not None:
                    failover_log.append(
                        {
                            "failover_from": provider,
                            "failover_to": nxt,
                            "reason": "budget_exhausted",
                        }
                    )
                prev_provider = provider
                continue

            key_str = keys_map.get(provider, "")
            if provider != "ollama" and not key_str:
                last_error = "missing_key"
                if prev_provider:
                    failover_log.append(
                        {
                            "failover_from": prev_provider,
                            "failover_to": provider,
                            "reason": "missing_key",
                        }
                    )
                prev_provider = provider
                continue

            attempt = 0
            http_tried = True
            while attempt < n_max:
                attempt += 1
                key_cell = [key_str]
                _inc_flight(provider)
                t0 = time.time()
                try:
                    norm = _call_provider(
                        provider,
                        model,
                        key_cell[0],
                        messages,
                        options,
                        cfg,
                    )
                except urllib.error.URLError:
                    norm = {
                        "error": True,
                        "http_status": 0,
                        "content": "",
                        "usage": {"tokens_in": 0, "tokens_out": 0},
                        "raw_response": {},
                    }
                finally:
                    key_cell[0] = ""
                    _dec_flight(provider)

                latency_ms = int((time.time() - t0) * 1000)
                http_st = int(norm.get("http_status", 200))

                if not norm.get("error"):
                    health.mark_ok(provider)
                    tin = int(norm["usage"]["tokens_in"])
                    tout = int(norm["usage"]["tokens_out"])
                    cost = pricing.compute_cost_usd(
                        provider, model, tin, tout, cfg
                    )
                    budget.commit_after_call(provider, cost)
                    completed = time.time()
                    total_lat = int((completed - started) * 1000)
                    receipt_path = _finish_receipt(
                        event="call.completed",
                        provider=provider,
                        model=model,
                        status="ok",
                        latency_ms=total_lat,
                        tokens_in=tin,
                        tokens_out=tout,
                        cost_usd=cost,
                        error_code=None,
                        content_ok=True,
                    )
                    out = {
                        "ok": True,
                        "content": norm["content"],
                        "usage": {"tokens_in": tin, "tokens_out": tout},
                        "call_id": call_id,
                        "provider": provider,
                        "model": model,
                        "receipt_path": receipt_path,
                    }
                    telemetry.record(
                        {
                            "call_id": call_id,
                            "agent_id": agent_id,
                            "provider": provider,
                            "model": model,
                            "latency_ms": total_lat,
                            "tokens_in": tin,
                            "tokens_out": tout,
                            "cost_usd": cost,
                            "status": "ok",
                            "error_code_if_any": None,
                            "started_at": _iso(started),
                            "completed_at": _iso(completed),
                        }
                    )
                    _LOG.info(
                        "fabric call_id=%s agent_id=%s provider=%s model=%s "
                        "latency_ms=%s status=%s",
                        call_id,
                        agent_id,
                        provider,
                        model,
                        total_lat,
                        "ok",
                    )
                    if leader_future is not None and isinstance(idem, str):
                        dedup.complete(agent_id, idem, out)
                    return out

                last_http = http_st
                code = f"http_{http_st}" if http_st else "network_error"
                last_error = code

                transient = http_st == 0 or is_transient_http_status(http_st)
                if transient and attempt < n_max:
                    continue
                break

            nxt = None
            try:
                idx = chain.index(provider)
                if idx + 1 < len(chain):
                    nxt = chain[idx + 1]
            except ValueError:
                nxt = None
            if nxt is not None:
                failover_log.append(
                    {
                        "failover_from": provider,
                        "failover_to": nxt,
                        "reason": last_error or "error",
                    }
                )
            prev_provider = provider

        completed = time.time()
        total_lat = int((completed - started) * 1000)
        if last_error == "missing_key":
            err_final = "missing_key"
        elif not http_tried and saw_budget_skip:
            err_final = "budget_exhausted"
        elif last_http is not None and (
            last_http == 0 or is_transient_http_status(last_http)
        ):
            err_final = "exhausted_retries"
        else:
            err_final = "provider_error"
        rec_event = (
            "call.refused_budget"
            if err_final == "budget_exhausted" and not http_tried
            else "call.failed"
        )
        receipt_path = _finish_receipt(
            event=rec_event,
            provider=prev_provider,
            model=None,
            status="error",
            latency_ms=total_lat,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            error_code=err_final,
            content_ok=False,
        )
        out: dict[str, Any] = {
            "ok": False,
            "error": err_final,
            "call_id": call_id,
            "receipt_path": receipt_path,
        }
        if err_final == "budget_exhausted":
            out["provider"] = chain[0] if chain else prev_provider
            out["reset_at"] = budget.next_reset_utc_midnight_ts()
        if last_http is not None:
            out["http_status"] = last_http
        telemetry.record(
            {
                "call_id": call_id,
                "agent_id": agent_id,
                "provider": prev_provider,
                "model": None,
                "latency_ms": total_lat,
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_usd": 0.0,
                "status": "error",
                "error_code_if_any": err_final,
                "started_at": _iso(started),
                "completed_at": _iso(completed),
            }
        )
        _LOG.info(
            "fabric call_id=%s agent_id=%s provider=%s model=%s "
            "latency_ms=%s status=%s",
            call_id,
            agent_id,
            prev_provider,
            None,
            total_lat,
            "error",
        )
        if leader_future is not None and isinstance(idem, str):
            dedup.complete(agent_id, idem, out)
        return out
    except Exception:
        if leader_future is not None and isinstance(idem, str):
            dedup.complete(
                agent_id,
                idem,
                {
                    "ok": False,
                    "error": "internal_error",
                    "call_id": call_id,
                    "receipt_path": receipt_path,
                },
            )
        raise


def status_snapshot(config_path: Path | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    bs = budget.budget_snapshot(cfg)
    providers: dict[str, Any] = {}
    for p in _VALID:
        snap = bs[p]
        last_ts = None
        raw_ts = health.last_ok_timestamp(p)
        if raw_ts is not None:
            last_ts = _iso(raw_ts)
        providers[p] = {
            "available": health.is_available(p),
            "last_ok_at": last_ts,
            "budget_used_today": snap["budget_used_today"],
            "budget_cap_today": snap["budget_cap_today"],
            "in_flight_count": inflight_for_provider(p),
        }
    ao = cfg.get("agent_overrides") or {}
    return {
        "providers": providers,
        "policy": {
            "default_chain": list(cfg.get("default_chain") or []),
            "agent_overrides_count": len(ao) if isinstance(ao, dict) else 0,
        },
        "today_totals": telemetry.today_totals(),
    }
