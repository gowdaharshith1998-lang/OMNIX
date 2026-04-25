"""Request adversarial value vectors from Provider Fabric (``task_kind: fuzz_inputs``)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from fabric import dispatcher

_LOG = logging.getLogger("omnix.verify.fuzz_fabric")

ENV_BUDGET = "OMNIX_FUZZ_FABRIC_BUDGET"
_DEFAULT_BUDGET = 5
_fuzz_llm_calls_remaining: int | None = None
TASK = "fuzz_inputs"


def reset_fuzz_fabric_budget_for_tests() -> None:
    global _fuzz_llm_calls_remaining
    _fuzz_llm_calls_remaining = None


def set_fuzz_fabric_remaining_for_tests(n: int) -> None:
    global _fuzz_llm_calls_remaining
    _fuzz_llm_calls_remaining = n


def _budget() -> int:
    raw = os.environ.get(ENV_BUDGET, str(_DEFAULT_BUDGET))
    try:
        return max(0, int(raw, 10))
    except ValueError:
        return _DEFAULT_BUDGET


def _ensure_remaining() -> int:
    global _fuzz_llm_calls_remaining
    if _fuzz_llm_calls_remaining is None:
        _fuzz_llm_calls_remaining = _budget()
    return int(_fuzz_llm_calls_remaining)


def _try_consume() -> bool:
    global _fuzz_llm_calls_remaining
    left = _ensure_remaining()
    if left <= 0:
        return False
    _fuzz_llm_calls_remaining = left - 1
    return True


def _parse_input_matrix(text: str) -> list[list[Any]]:
    s = (text or "").strip()
    if not s:
        return []
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.I)
    m = re.search(r"\[.*\]", s, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0) if m else s)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    if data and not isinstance(data[0], list):
        return [data]  # type: ignore[return-value]
    return [list(x) for x in data if isinstance(x, (list, tuple))]


def request_adversarial_inputs_from_fabric(
    agent_id: str,
    language: str,
    signature: str,
    param_hint: str,
) -> tuple[list[list[Any]], str, dict[str, Any] | None]:
    """
    Returns (inputs, reason, last_dispatch) — budget refusal yields ([], "budget", None).
    """
    if os.environ.get("OMNIX_FUZZ_MOCK") == "1":
        return (
            [
                [0, -1],
                [1, 2**16],
            ],
            "mock",
            None,
        )
    if not _try_consume():
        return [], "budget_exhausted", None
    from pathlib import Path
    msg = {
        "agent_id": agent_id,
        "task_kind": TASK,
        "provider_key": {
            "provider": "ollama",
            "key": os.environ.get("OMNIX_AI_KEY", "x"),
        },
        "options": {
            "timeout_ms": 15000,
        },
        "messages": [
            {
                "role": "user",
                "content": (
                    f"Return ONLY a JSON 2D array: list of argument vectors for a fuzzer.\n"
                    f"Language={language!r} signature={signature!r} hint={param_hint!r}\n"
                    f"Example: [[0,0],[1,-1]]"
                ),
            },
        ],
    }
    try:
        out = dispatcher.dispatch(
            msg,
            config_path=Path.home() / ".omnix" / "fabric_config.json",
        )
    except (OSError, ValueError, TypeError) as e:
        _LOG.debug("dispatch fuzz_inputs: %s", e)
        return [], f"error:{e!s}"[:200], None
    if not isinstance(out, dict) or not out.get("ok"):
        return (
            [],
            f"ok_false:{(out or {}).get('error', 'unknown')}"[:200],
            out,
        )
    cont = (out.get("message") or {}).get("content") or ""
    ar = _parse_input_matrix(str(cont))
    return (ar, "ok", out)
