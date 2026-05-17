"""Assemble ``find_bugs`` receipt JSON and sign with ML-DSA-65 (``verify.receipt``)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omnix.verify import receipt


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def codebase_fingerprint(rel_size_pairs: list[tuple[str, int]]) -> str:
    """sha256 of sorted (path, size) lines, paths UTF-8."""
    lines = "\n".join(f"{p}\t{sz}" for p, sz in sorted(rel_size_pairs, key=lambda x: x[0]))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def _sanitize_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", name)[:200] or "codebase"


def assemble_and_sign(
    target: dict[str, Any],
    summary: dict[str, Any],
    findings: list[dict[str, Any]],
    import_errors: list[dict[str, Any]],
    timeout_skips: list[dict[str, Any]],
    graph_signals: dict[str, Any],
    *,
    skipped_main: list[dict[str, Any]] | None = None,
    no_sign: bool = False,
) -> str:
    sm = list(skipped_main) if skipped_main else []
    body: dict[str, Any] = {
        "version": 1,
        "kind": "find_bugs",
        "timestamp": utc_now_iso(),
        "target": target,
        "summary": summary,
        "findings": findings,
        "import_errors": list(import_errors),
        "timeout_skips": list(timeout_skips),
        "skipped_main": sm,
        "graph_signals": graph_signals,
    }
    if no_sign:
        out = {**body, "axiom_signature": None}
        return json.dumps(
            out, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    return receipt.mint_signed_receipt(body)


def write_bundle(
    json_text: str,
    receipt_dir: Path,
    *,
    codebase_name: str,
) -> Path:
    tflat = utc_now_iso().replace(":", "-")
    d = Path(receipt_dir) if str(receipt_dir) else Path.home() / ".omnix" / "receipts"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"find_bugs_{tflat}_{_sanitize_name(codebase_name)}.json"
    p.write_text(json_text, encoding="utf-8")
    return p
