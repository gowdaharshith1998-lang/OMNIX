"""src/fabric/providers/anthropic.py — Anthropic Messages API adapter
Compliance: P11, P20, P22
"""

from __future__ import annotations

from typing import Any

from omnix.fabric.providers import common

_API = "https://api.anthropic.com/v1/messages"


def call(
    *,
    model: str,
    api_key: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    timeout_s: float,
) -> tuple[int, dict[str, Any]]:
    system_chunks: list[str] = []
    msgs: list[dict[str, str]] = []
    for m in messages:
        role = m.get("role", "user")
        content = str(m.get("content", ""))
        if role == "system":
            system_chunks.append(content)
        elif role in ("user", "assistant"):
            msgs.append({"role": role, "content": content})
    body: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "messages": msgs}
    if system_chunks:
        body["system"] = "\n".join(system_chunks)
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    status, data = common.request_json(
        _API, method="POST", headers=headers, body=body, timeout_s=timeout_s
    )
    return status, data if isinstance(data, dict) else {"raw": data}


def normalize_response(status: int, data: dict[str, Any]) -> dict[str, Any]:
    if status >= 400:
        return {
            "error": True,
            "http_status": status,
            "content": "",
            "usage": {"tokens_in": 0, "tokens_out": 0},
            "raw_response": {"status": status},
        }
    text = ""
    for block in data.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text += str(block.get("text", ""))
    usage = data.get("usage") or {}
    return {
        "error": False,
        "http_status": status,
        "content": text,
        "usage": {
            "tokens_in": int(usage.get("input_tokens", 0)),
            "tokens_out": int(usage.get("output_tokens", 0)),
        },
        "raw_response": {"status": status},
    }
