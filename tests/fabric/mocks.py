"""Shared mock HTTP responses for provider adapters (urllib.request.urlopen)."""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock


def _resp(body: dict[str, Any] | str, status: int = 200) -> MagicMock:
    raw = body if isinstance(body, str) else json.dumps(body)
    m = MagicMock()
    m.status = status
    m.__enter__ = lambda s: s
    m.__exit__ = lambda *a: None
    m.read = lambda: raw.encode("utf-8") if isinstance(raw, str) else raw
    return m


def anthropic_ok(
    text: str = "hello",
    in_tok: int = 10,
    out_tok: int = 5,
) -> MagicMock:
    return _resp(
        {
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
        }
    )


def openai_ok(
    text: str = "hello",
    in_tok: int = 10,
    out_tok: int = 5,
) -> MagicMock:
    return _resp(
        {
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": in_tok, "completion_tokens": out_tok},
        }
    )


def google_ok(
    text: str = "hello",
    in_tok: int = 10,
    out_tok: int = 5,
) -> MagicMock:
    return _resp(
        {
            "candidates": [
                {"content": {"parts": [{"text": text}], "role": "model"}}
            ],
            "usageMetadata": {
                "promptTokenCount": in_tok,
                "candidatesTokenCount": out_tok,
            },
        }
    )


def ollama_ok(
    text: str = "hello",
    in_tok: int = 10,
    out_tok: int = 5,
) -> MagicMock:
    return _resp(
        {
            "message": {"role": "assistant", "content": text},
            "prompt_eval_count": in_tok,
            "eval_count": out_tok,
        }
    )


def http_error(status: int, body: str = "{}") -> Any:
    import urllib.error

    return urllib.error.HTTPError(
        "https://example.invalid",
        status,
        "err",
        hdrs={},  # type: ignore[arg-type]
        fp=BytesIO(body.encode("utf-8")),
    )
