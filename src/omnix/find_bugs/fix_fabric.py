"""Provider Fabric ``code_fix`` task (P28: only when ``--fix``)."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from omnix.fabric import dispatcher

_LOG = logging.getLogger("omnix.find_bugs.fix_fabric")

ENV_BUDGET = "OMNIX_CODE_FIX_FABRIC_BUDGET"
_DEFAULT = 3
_calls_left: int | None = None
TASK = "code_fix"


def reset_code_fix_budget_for_tests() -> None:
    global _calls_left
    _calls_left = None


def set_code_fix_remaining_for_tests(n: int) -> None:
    global _calls_left
    _calls_left = n


def _remaining() -> int:
    global _calls_left
    if _calls_left is None:
        try:
            _calls_left = max(0, int(os.environ.get(ENV_BUDGET, str(_DEFAULT)), 10))
        except ValueError:  # pragma: no cover
            _calls_left = _DEFAULT
    return int(_calls_left)


def _consume() -> bool:
    global _calls_left
    n = _remaining()
    if n <= 0:
        return False
    _calls_left = n - 1
    return True


def request_code_fix(
    agent_id: str, prompt_user: str
) -> tuple[dict[str, Any] | None, str, Any]:
    if os.environ.get("OMNIX_CODE_FIX_MOCK") == "1":
        fix = (
            "def divide(x, y):\n"
            "    if y == 0:\n"
            "        return 0\n"
            "    return x / y\n"
        )
        return ({"python_full_file": fix}, "mock", None)
    if not _consume():
        return None, "budget", None
    if os.environ.get("OMNIX_FABRIC_DRY", "").lower() in ("1", "true", "yes"):
        return None, "dry", None
    msg: dict[str, Any] = {
        "agent_id": agent_id,
        "task_kind": TASK,
        "provider_key": {
            "provider": "ollama",
            "key": os.environ.get("OMNIX_AI_KEY", "x"),
        },
        "options": {"timeout_ms": 120_000},
        "messages": [
            {
                "role": "user",
                "content": (
                    f"{_schema_blurb()}\n\n{prompt_user}"
                )[:200_000],
            },
        ],
    }
    try:
        out = dispatcher.dispatch(
            msg,
            config_path=Path.home() / ".omnix" / "fabric_config.json",
        )
    except (OSError, ValueError, TypeError) as e:  # pragma: no cover
        _LOG.debug("code_fix: %s", e)
        return None, f"err:{e!s}"[:120], None
    if not isinstance(out, dict) or not out.get("ok"):
        return None, str((out or {}).get("error", "nok"))[:200], out
    cont = (out.get("message") or {}).get("content") or ""
    return _parse_model_json(str(cont)), "ok", out


def _schema_blurb() -> str:
    return (
        "Return a single JSON object (no markdown) with one of:\n"
        '  {"python_full_file": "entire .py file content as UTF-8"}\n'
        '  or {"unified_diff": "unified diff against the failing file only"}\n'
    )


def _parse_model_json(t: str) -> dict[str, Any] | None:
    t = t.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I)
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if not m:
        return None
    try:
        o = json.loads(m.group(0) if m else t)
    except json.JSONDecodeError:  # pragma: no cover
        return None
    return o if isinstance(o, dict) else None
