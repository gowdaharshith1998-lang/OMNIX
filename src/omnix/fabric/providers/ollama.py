"""src/fabric/providers/ollama.py — Ollama /api/chat adapter
Compliance: P11, P20, P22
"""

from __future__ import annotations

from typing import Any

from omnix.fabric.providers import common


def call(
    *,
    model: str,
    api_key: str,
    base_url: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    timeout_s: float,
) -> tuple[int, dict[str, Any]]:
    _ = api_key
    omsgs: list[dict[str, str]] = []
    for m in messages:
        role = m.get("role", "user")
        if role == "system":
            role = "user"
        if role not in ("user", "assistant"):
            role = "user"
        omsgs.append({"role": role, "content": str(m.get("content", ""))})
    url = base_url.rstrip("/") + "/api/chat"
    body = {
        "model": model,
        "messages": omsgs,
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    status, data = common.request_json(
        url, method="POST", headers={}, body=body, timeout_s=timeout_s
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
    msg = data.get("message") or {}
    text = str(msg.get("content", ""))
    return {
        "error": False,
        "http_status": status,
        "content": text,
        "usage": {
            "tokens_in": int(data.get("prompt_eval_count", 0)),
            "tokens_out": int(data.get("eval_count", 0)),
        },
        "raw_response": {"status": status},
    }
