"""src/fabric/providers/google.py — Gemini generateContent adapter
Compliance: P11, P20, P22, P23
"""

from __future__ import annotations

import logging
from typing import Any

from omnix.fabric.providers import common

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_LOG = logging.getLogger(__name__)


def _build_url(model: str, api_key: str) -> str:
    return f"{_BASE}/{model}:generateContent?key={api_key}"


def call(
    *,
    model: str,
    api_key: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    timeout_s: float,
) -> tuple[int, dict[str, Any]]:
    _ = max_tokens
    contents: list[dict[str, Any]] = []
    system_parts: list[str] = []
    for m in messages:
        role = m.get("role", "user")
        text = str(m.get("content", ""))
        if role == "system":
            system_parts.append(text)
            continue
        grole = "model" if role == "assistant" else "user"
        contents.append({"role": grole, "parts": [{"text": text}]})
    body: dict[str, Any] = {"contents": contents}
    if system_parts:
        body["systemInstruction"] = {
            "parts": [{"text": "\n".join(system_parts)}]
        }
    url = _build_url(model, api_key)
    if _LOG.isEnabledFor(logging.INFO):
        _LOG.info("google request %s", common.redact_url_for_log(url))
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
    text = ""
    cands = data.get("candidates") or []
    if cands and isinstance(cands[0], dict):
        content = cands[0].get("content") or {}
        for p in content.get("parts") or []:
            if isinstance(p, dict) and "text" in p:
                text += str(p["text"])
    um = data.get("usageMetadata") or {}
    return {
        "error": False,
        "http_status": status,
        "content": text,
        "usage": {
            "tokens_in": int(um.get("promptTokenCount", 0)),
            "tokens_out": int(um.get("candidatesTokenCount", 0)),
        },
        "raw_response": {"status": status},
    }
