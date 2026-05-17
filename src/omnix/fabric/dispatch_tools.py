"""Tool-aware wrapper around provider-client chat — multi-turn LLM tool-use (slice 15.3.7)."""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import replace
from typing import Any

from omnix.providers.registry import PROVIDERS
from omnix.providers.tools import ToolContext, ToolStep, execute_tools, run_tool
from omnix.providers.tools.definitions import (
    build_tool_definitions,
    summarize_tool_args,
    tool_shape_for_provider,
)

_LOG = logging.getLogger(__name__)

MAX_ITERATIONS = 10
MAX_TOTAL_TOKENS = 200_000
WALL_CLOCK_S = 60.0
PER_TURN_S = 30.0
PER_TOOL_S = 5.0


def _step_dict(step: ToolStep) -> dict[str, Any]:
    return {
        "tool": step.tool,
        "status": step.status,
        "result": step.result,
        "truncated": step.truncated,
        "error": step.error,
        "turn_number": step.turn_number,
        "args_summary": step.args_summary,
        "phase": step.phase,
        "tool_call_id": step.tool_call_id,
    }


def _steps_for_seed_prompt(steps: list[ToolStep]) -> list[dict[str, Any]]:
    return [
        {
            "tool": step.tool,
            "status": step.status,
            "result": step.result,
            "truncated": step.truncated,
            "error": step.error,
        }
        for step in steps
    ]


def _adapter_supports_llm_tools(provider: str) -> bool:
    spec = PROVIDERS.get(provider)
    if not spec:
        return False
    return spec.adapter in ("openai_compatible", "anthropic")


def _tool_payload_json(step: ToolStep) -> str:
    return json.dumps(
        {
            "tool": step.tool,
            "status": step.status,
            "result": step.result,
            "error": step.error,
            "truncated": step.truncated,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _inject_seed_and_tool_preamble(
    messages: list[dict[str, Any]],
    *,
    seed_steps: list[ToolStep],
    tool_names: list[str],
) -> list[dict[str, Any]]:
    parts: list[str] = []
    if seed_steps:
        ok_lines = _steps_for_seed_prompt(
            [s for s in seed_steps if s.status == "ok"]
        )
        if ok_lines:
            parts.append(
                "Initial context (prefetched from your selection / request):\n"
                + json.dumps(ok_lines, sort_keys=True, ensure_ascii=False)
            )
    preamble = (
        "You have access to OMNIX's code intelligence tools. "
        + (parts[0] + "\n\n" if parts else "")
        + "Available tools: "
        + ", ".join(tool_names)
        + ".\n\n"
        "Use these tools to gather graph and source facts before answering. "
        "Call tools with concrete node_id values (format: 'path/to/file.py::symbol')."
    )
    out = [dict(m) for m in messages]
    if out and str(out[0].get("role")) == "system":
        c = out[0].get("content", "")
        out[0] = {**out[0], "content": str(c) + "\n\n" + preamble}
    else:
        out.insert(0, {"role": "system", "content": preamble})
    return out


def _run_tool_with_timeout(
    name: str,
    ctx: ToolContext,
    args: dict[str, Any],
    *,
    timeout_s: float,
) -> ToolStep:
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(run_tool, name, ctx, args)
        try:
            return fut.result(timeout=timeout_s)
        except FuturesTimeout:
            return ToolStep(
                tool=name,
                status="error",
                result={},
                error=f"tool execution exceeded {timeout_s:.0f}s",
            )
        except Exception as e:  # noqa: BLE001
            return ToolStep(tool=name, status="error", result={}, error=str(e))


def dispatch_with_tools(
    client: Any,
    *,
    messages: list[dict[str, str]],
    model: str | None,
    tools: list[str],
    tool_context: ToolContext | None,
    tool_args: dict[str, Any] | None = None,
    provider_override: str | None = None,
) -> dict[str, Any]:
    started = time.time()
    provider = str(getattr(client, "provider", ""))
    degraded_ollama = bool(tools and provider == "ollama")
    all_steps: list[ToolStep] = []
    capped = False
    cap_reason: str | None = None
    iterations = 0
    total_in = 0
    total_out = 0

    if not tools:
        result = client.chat(
            list(messages),
            model=model,
            task_kind="action-dispatch",
            provider_override=provider_override,
        )
        out = dict(result)
        out["tool_steps"] = []
        out["cost_cap_triggered"] = False
        out["capped"] = False
        out["cap_reason"] = None
        out["iterations"] = 0
        out["latency_ms"] = int((time.time() - started) * 1000)
        return out

    if degraded_ollama:
        tool_steps = [
            ToolStep(
                tool=name,
                status="degraded",
                result={
                    "reason": "provider_does_not_support_tool_use_reliably",
                },
                phase="seed",
                turn_number=0,
            )
            for name in tools
        ]
        outbound = list(messages)
        outbound.append(
            {
                "role": "system",
                "content": (
                    "Tool context is unavailable for this Ollama model. "
                    "Answer from the supplied prompt and clearly note any uncertainty."
                ),
            }
        )
        result = client.chat(
            outbound,
            model=model,
            task_kind="action-dispatch",
            provider_override=provider_override,
        )
        out = dict(result)
        out["tool_steps"] = [_step_dict(s) for s in tool_steps]
        out["cost_cap_triggered"] = any(s.truncated for s in tool_steps)
        out["capped"] = False
        out["cap_reason"] = None
        out["iterations"] = 0
        out["latency_ms"] = int((time.time() - started) * 1000)
        return out

    seed_steps: list[ToolStep] = []
    if tool_context is not None and tool_args:
        raw_seed = execute_tools(tools, tool_context, tool_args)
        seed_steps = [replace(s, phase="seed", turn_number=0) for s in raw_seed]
        all_steps.extend(seed_steps)

    outbound: list[dict[str, Any]] = [dict(m) for m in messages]
    outbound = _inject_seed_and_tool_preamble(
        outbound, seed_steps=seed_steps, tool_names=list(tools)
    )

    if not _adapter_supports_llm_tools(provider):
        if tools and tool_context is not None:
            _LOG.info("tool_use_unsupported_provider %s — prefetch/seed only", provider)
        result = client.chat(
            outbound,
            model=model,
            task_kind="action-dispatch",
            provider_override=provider_override,
        )
        out = dict(result)
        out["tool_steps"] = [_step_dict(s) for s in all_steps]
        out["cost_cap_triggered"] = any(s.truncated for s in all_steps)
        out["capped"] = False
        out["cap_reason"] = None
        out["iterations"] = 0
        out["latency_ms"] = int((time.time() - started) * 1000)
        return out

    if tool_context is None:
        result = client.chat(
            outbound,
            model=model,
            task_kind="action-dispatch",
            provider_override=provider_override,
        )
        out = dict(result)
        out["tool_steps"] = []
        out["cost_cap_triggered"] = False
        out["capped"] = False
        out["cap_reason"] = None
        out["iterations"] = 0
        out["latency_ms"] = int((time.time() - started) * 1000)
        return out

    defs = build_tool_definitions(list(tools), tool_shape_for_provider(provider))
    messages_oai: list[dict[str, Any]] = list(outbound)

    final_text = ""
    last_result: dict[str, Any] = {}
    natural_finish = False

    for turn_idx in range(MAX_ITERATIONS):
        if time.time() - started > WALL_CLOCK_S:
            capped = True
            cap_reason = "wall_clock"
            break
        if total_in + total_out > MAX_TOTAL_TOKENS:
            capped = True
            cap_reason = "token_limit"
            break

        turn_no = turn_idx + 1
        turn_started = time.time()
        result = client.chat(
            messages_oai,
            model=model,
            task_kind="action-dispatch",
            provider_override=provider_override,
            tool_definitions=defs,
            options={
                "timeout_ms": int(PER_TURN_S * 1000),
            },
        )
        turn_elapsed = time.time() - turn_started
        if turn_elapsed > PER_TURN_S:
            capped = True
            cap_reason = "per_turn_timeout"
            break

        last_result = dict(result)
        if not result.get("ok"):
            out = dict(result)
            out["tool_steps"] = [_step_dict(s) for s in all_steps]
            out["cost_cap_triggered"] = any(s.truncated for s in all_steps)
            out["capped"] = capped
            out["cap_reason"] = cap_reason
            out["iterations"] = turn_no
            out["latency_ms"] = int((time.time() - started) * 1000)
            return out

        usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
        total_in += int(usage.get("tokens_in") or 0)
        total_out += int(usage.get("tokens_out") or 0)
        iterations = turn_no

        tcalls = result.get("tool_calls")
        text = str(result.get("content") or "")

        if not tcalls:
            final_text = text
            natural_finish = True
            break

        asst: dict[str, Any] = {
            "role": "assistant",
            "content": text if text.strip() else None,
        }
        asst["tool_calls"] = tcalls
        messages_oai.append(asst)

        for tc in tcalls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            name = str(fn.get("name", ""))
            args_raw = fn.get("arguments", "{}")
            try:
                args = (
                    json.loads(args_raw)
                    if isinstance(args_raw, str)
                    else (args_raw or {})
                )
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            tid = str(tc.get("id", ""))
            summary = summarize_tool_args(name, args)

            if name not in tools:
                step = ToolStep(
                    tool=name or "unknown",
                    status="error",
                    result={},
                    error="tool_not_allowed_for_this_action",
                    turn_number=turn_no,
                    args_summary=summary,
                    phase="llm",
                    tool_call_id=tid or None,
                )
            else:
                base_step = _run_tool_with_timeout(
                    name,
                    tool_context,
                    args,
                    timeout_s=PER_TOOL_S,
                )
                step = replace(
                    base_step,
                    turn_number=turn_no,
                    args_summary=summary,
                    phase="llm",
                    tool_call_id=tid or None,
                )
            all_steps.append(step)
            messages_oai.append(
                {
                    "role": "tool",
                    "tool_call_id": tid,
                    "content": _tool_payload_json(step),
                }
            )
    else:
        capped = True
        cap_reason = "max_iterations"

    if natural_finish and last_result:
        out = dict(last_result)
        out["content"] = final_text
    elif last_result:
        out = dict(last_result)
        if not out.get("content") and final_text:
            out["content"] = final_text
    else:
        out = {
            "ok": False,
            "error": "dispatch_error",
            "content": "",
            "usage": {"tokens_in": total_in, "tokens_out": total_out},
        }

    out["tool_steps"] = [_step_dict(s) for s in all_steps]
    out["cost_cap_triggered"] = bool(
        capped or any(s.truncated for s in all_steps)
    )
    out["capped"] = capped
    out["cap_reason"] = cap_reason
    out["iterations"] = iterations
    out["latency_ms"] = int((time.time() - started) * 1000)
    out["usage"] = {
        "tokens_in": total_in,
        "tokens_out": total_out,
    }
    return out
