"""LLM-based graph completion when AST quality is low (Provider Fabric, P12–P14)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from omnix.fabric import dispatcher
from omnix.graph.store import GraphStore

_LOG = logging.getLogger("omnix.parser.llm")

TASK_KIND_PARSE_EXTRACT = "parse_extract"
ENV_BUDGET = "OMNIX_LLM_FALLBACK_BUDGET"
_DEFAULT_BUDGET = 5

# Remaining calls for the current find-bugs / analyze run. None = read env on first use.
_llm_calls_remaining: int | None = None


def _budget_from_env() -> int:
    raw = os.environ.get(ENV_BUDGET, str(_DEFAULT_BUDGET))
    try:
        n = int(raw, 10)
    except ValueError:
        n = _DEFAULT_BUDGET
    return max(0, n)


def reset_llm_fallback_budget_for_tests() -> None:
    global _llm_calls_remaining
    _llm_calls_remaining = None


def _ensure_budget() -> int:
    global _llm_calls_remaining
    if _llm_calls_remaining is None:
        _llm_calls_remaining = _budget_from_env()
    return int(_llm_calls_remaining)


def set_llm_fallback_remaining_for_tests(n: int) -> None:
    global _llm_calls_remaining
    _llm_calls_remaining = n


def _try_consume_budget() -> bool:
    global _llm_calls_remaining
    left = _ensure_budget()
    if left <= 0:
        return False
    _llm_calls_remaining = left - 1
    return True


def _n_lines(s: str) -> int:
    if not s:
        return 0
    return s.count("\n") + 1


@dataclass(frozen=True)
class LlmFallbackResult:
    called_llm: bool
    reason: str
    """Machine token for logging / tests — not user-facing copy."""

    parse_mode: str
    """``llm`` if merged, ``empty`` (P12 short file), or ``no_llm``."""

    quality_score: float
    """Reported 0.0 for P12 short files, else the input *quality_score*."""


def _extraction_json_schema_blurb() -> str:
    return (
        "Return a single JSON object (no markdown, no prose) with this shape only:\n"
        '{"functions":[{"name":"str","line":1,"params":["str"]}],\n'
        '"classes":[{"name":"str","line":1}],\n'
        '"calls":[{"caller":"str","callee":"str","line":1}],\n'
        '"imports": ["str"]}\n'
    )


def _build_messages(rel: str, text: str, language: str) -> list[dict[str, str]]:
    u = _extraction_json_schema_blurb()
    user = f"{u}\nFile: {rel}\nLanguage hint: {language}\n-----\n" f"{text}"
    return [
        {
            "role": "system",
            "content": "You are a static-analysis extractor. Output valid JSON only.",
        },
        {"role": "user", "content": user},
    ]


def _parse_model_json(text: str) -> dict[str, Any]:
    t = text.strip()
    start = None
    for i, ch in enumerate(t):
        if ch in "{[":
            start = i
            break
    if start is None:
        raise ValueError("no json")
    t2 = t[start:]
    depth = 0
    for j, ch in enumerate(t2):
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return json.loads(t2[: j + 1])
    return json.loads(t2)


def _merge_llm_extraction(
    store: GraphStore, rel: str, data: dict[str, Any]
) -> None:
    fns = data.get("functions")
    if isinstance(fns, list):
        for it in fns:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name", "")).strip() or "anonymous_fn"
            line = int(it.get("line") or 0) or 1
            p = it.get("params")
            pr: list[str] | str | None
            if isinstance(p, list):
                pr = [str(x) for x in p]
            elif p is None:
                pr = None
            else:
                pr = str(p)
            store.add_node(
                id=f"{rel}::{name}",
                name=name,
                type="function",
                file_path=rel,
                start_line=line,
                end_line=line,
                complexity=1,
                metadata={"source": "llm", "params": pr},
            )
    cl = data.get("classes")
    if isinstance(cl, list):
        for it in cl:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name", "")).strip() or "anonymous_cl"
            line = int(it.get("line") or 0) or 1
            store.add_node(
                id=f"{rel}::{name}",
                name=name,
                type="class",
                file_path=rel,
                start_line=line,
                end_line=line,
                complexity=1,
                metadata={"source": "llm"},
            )
    calls = data.get("calls")
    if isinstance(calls, list):
        for it in calls:
            if not isinstance(it, dict):
                continue
            ca = str(it.get("caller", "")).strip()
            ce = str(it.get("callee", "")).strip()
            if not ca or not ce:
                continue
            sid = f"{rel}::{ca}"
            tid = f"{rel}::{ce}"
            store.add_edge(
                sid, tid, "CALLS", metadata={"source": "llm", "line": it.get("line")}
            )
    imps = data.get("imports")
    if isinstance(imps, list):
        for m in imps:
            if not isinstance(m, str) or not m.strip():
                continue
            iid = f"{rel}::import::llm::{m}"
            line = 1
            store.add_node(
                id=iid,
                name=m,
                type="import",
                file_path=rel,
                start_line=line,
                end_line=line,
                complexity=1,
                metadata={"source": "llm", "module": m},
            )
            store.add_edge(rel, iid, "IMPORTS", metadata={"source": "llm"})


def try_llm_fallback(
    store: GraphStore,
    rel: str,
    text: str,
    *,
    quality_score: float,
    language: str = "unknown",
    provider_key: dict[str, str] | None = None,
) -> LlmFallbackResult:
    """
    When AST extraction is poor (quality < 0.4) and the file is not trivially
    small, run one Fabric call and merge structured JSON. P12: ``n_lines < 5``
    forces *parse_mode* ``empty``, *quality* 0.0, and no network call. P14:
    prose in the model reply is dropped after JSON parse.
    """
    n = _n_lines(text)
    if n < 5:
        return LlmFallbackResult(
            called_llm=False,
            reason="p12_too_few_lines",
            parse_mode="empty",
            quality_score=0.0,
        )
    if quality_score >= 0.7:
        return LlmFallbackResult(
            called_llm=False,
            reason="quality_good_enough",
            parse_mode="no_llm",
            quality_score=quality_score,
        )
    if quality_score >= 0.4:
        return LlmFallbackResult(
            called_llm=False,
            reason="ast_above_low_threshold",
            parse_mode="no_llm",
            quality_score=quality_score,
        )
    if _ensure_budget() <= 0:
        _LOG.warning("llm fallback budget exhausted: file=%s", rel)
        return LlmFallbackResult(
            called_llm=False,
            reason="budget_exhausted",
            parse_mode="no_llm",
            quality_score=quality_score,
        )
    pk = provider_key
    if not isinstance(pk, dict) or "provider" not in pk:
        return LlmFallbackResult(
            called_llm=False,
            reason="no_provider_key",
            parse_mode="no_llm",
            quality_score=quality_score,
        )
    if not _try_consume_budget():
        return LlmFallbackResult(
            called_llm=False,
            reason="budget_exhausted",
            parse_mode="no_llm",
            quality_score=quality_score,
        )
    out = dispatcher.dispatch(  # type: ignore[no-untyped-call]
        {
            "agent_id": "omnix_universal",
            "task_kind": TASK_KIND_PARSE_EXTRACT,
            "messages": _build_messages(rel, text, language),
            "provider_key": {
                "provider": str(pk["provider"]),
                "key": str(pk.get("key", "")),
            },
            "options": {
                "max_tokens": 4096,
                "timeout_ms": 60_000,
            },
        }
    )
    if not out.get("ok"):
        _LOG.warning("llm fallback failed file=%s err=%s", rel, out.get("error"))
        return LlmFallbackResult(
            called_llm=True,
            reason="dispatch_error",
            parse_mode="no_llm",
            quality_score=quality_score,
        )
    content = out.get("content")
    if not isinstance(content, str) or not content.strip():
        return LlmFallbackResult(
            called_llm=True,
            reason="no_content",
            parse_mode="no_llm",
            quality_score=quality_score,
        )
    try:
        j = _parse_model_json(content)
    except (json.JSONDecodeError, ValueError) as e:
        _LOG.warning("llm fallback bad json file=%s err=%s", rel, e)
        return LlmFallbackResult(
            called_llm=True,
            reason="json_parse_error",
            parse_mode="no_llm",
            quality_score=quality_score,
        )
    if not isinstance(j, dict):
        return LlmFallbackResult(
            called_llm=True,
            reason="not_object",
            parse_mode="no_llm",
            quality_score=quality_score,
        )
    _merge_llm_extraction(store, rel, j)
    store.commit()
    return LlmFallbackResult(
        called_llm=True, reason="merged", parse_mode="llm", quality_score=quality_score
    )
