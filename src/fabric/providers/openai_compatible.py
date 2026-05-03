"""OpenAI-compatible Chat Completions adapter.

Used for OpenAI plus provider endpoints that implement the OpenAI chat shape.
"""

from __future__ import annotations

from typing import Any

from fabric.providers import common

_DEFAULT_BASE_URL = "https://api.openai.com/v1"


def call(
    *,
    model: str,
    api_key: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    timeout_s: float,
    base_url: str | None = None,
    chat_endpoint: str = "/chat/completions",
) -> tuple[int, dict[str, Any]]:
    openai_msgs: list[dict[str, str]] = []
    for m in messages:
        role = m.get("role", "user")
        if role not in ("user", "assistant", "system"):
            role = "user"
        openai_msgs.append({"role": role, "content": str(m.get("content", ""))})
    body: dict[str, Any] = {
        "model": model,
        "messages": openai_msgs,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    root = (base_url or _DEFAULT_BASE_URL).rstrip("/")
    endpoint = chat_endpoint if chat_endpoint.startswith("/") else f"/{chat_endpoint}"
    status, data = common.request_json(
        root + endpoint,
        method="POST",
        headers=headers,
        body=body,
        timeout_s=timeout_s,
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
    choices = data.get("choices") or []
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message") or {}
        text = str(msg.get("content", ""))
    usage = data.get("usage") or {}
    return {
        "error": False,
        "http_status": status,
        "content": text,
        "usage": {
            "tokens_in": int(usage.get("prompt_tokens", 0)),
            "tokens_out": int(usage.get("completion_tokens", 0)),
        },
        "raw_response": {"status": status},
    }
