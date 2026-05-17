"""Shared grammar DB queries for CLI and Studio API (read-only)."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def resolve_db_path(explicit: str | None, *, search_from: Path | None = None) -> Path:
    """Walk upward from *search_from* (default: CWD) for ``.omnix/omnix.db``."""
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(
                f"Database file not found or not a file: {p}",
            )
        return p

    start = (search_from or Path.cwd()).resolve()
    for parent in [start, *start.parents]:
        candidate = parent / ".omnix" / "omnix.db"
        if candidate.is_file():
            return candidate.resolve()

    raise FileNotFoundError(
        "No .omnix/omnix.db found in this directory or any parent. "
        "Run `omnix analyze .` (or `python omnix.py analyze <path>`) first, "
        "or pass --db /path/to/omnix.db.",
    )


def open_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = 1;")
    return conn


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def collect_grammar_status(
    conn: sqlite3.Connection,
    grammar_filter: str | None,
) -> dict[str, Any]:
    """Aggregate per-grammar rows plus footer data. All queries parameterized."""
    params: tuple[Any, ...] = ()
    where_grammar = ""
    if grammar_filter:
        where_grammar = " WHERE grammar_name = ? "
        params = (grammar_filter,)

    grammar_rows = conn.execute(
        "SELECT grammar_name, total_files_parsed, total_quality_score "
        "FROM grammar_profile" + where_grammar + " ORDER BY grammar_name",
        params,
    ).fetchall()

    grammars: list[dict[str, Any]] = []
    for row in grammar_rows:
        g = str(row["grammar_name"])
        tf = int(row["total_files_parsed"] or 0)
        tq = float(row["total_quality_score"] or 0.0)
        avg_q = round((tq / tf), 3) if tf else 0.0

        n_pat = conn.execute(
            "SELECT COUNT(*) FROM query_pattern WHERE grammar_name = ?",
            (g,),
        ).fetchone()[0]

        n_mut_30 = conn.execute(
            "SELECT COUNT(*) FROM pattern_mutation WHERE grammar_name = ? "
            "AND observed_at >= datetime('now', '-30 days')",
            (g,),
        ).fetchone()[0]

        last_r = conn.execute(
            "SELECT receipt_path FROM pattern_mutation WHERE grammar_name = ? "
            "ORDER BY observed_at DESC LIMIT 1",
            (g,),
        ).fetchone()
        receipt = ""
        if last_r and last_r[0] is not None:
            receipt = str(last_r[0]).strip()
        if not receipt:
            receipt_out: str | None = None
        else:
            receipt_out = receipt

        grammars.append(
            {
                "grammar_name": g,
                "files_parsed": tf,
                "avg_quality": avg_q,
                "parse_modes": {},
                "active_patterns": int(n_pat),
                "recent_mutations_30d": int(n_mut_30),
                "last_evolution_receipt": receipt_out,
            }
        )

    unk_rows = conn.execute(
        "SELECT extension FROM unknown_extensions ORDER BY extension ASC",
    ).fetchall()
    unknown_extensions: list[dict[str, Any]] = [
        {"ext": str(r["extension"]), "count": 1} for r in unk_rows
    ]
    top3 = [str(r["extension"]) for r in unk_rows[:3]]

    return {
        "grammars": grammars,
        "unknown_extensions": unknown_extensions,
        "unknown_extensions_top3": top3,
        "llm_fallback": {"calls": None, "budget_remaining": "n/a"},
    }


def collect_mutations(
    conn: sqlite3.Connection,
    grammar_filter: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Recent pattern_mutation rows ordered by observed_at DESC."""
    lim = min(max(int(limit), 1), 500)
    sql = (
        "SELECT grammar_name, mutation_kind, reason, observed_at, receipt_path, sig_path "
        "FROM pattern_mutation WHERE 1=1"
    )
    params: list[Any] = []
    if grammar_filter:
        sql += " AND grammar_name = ?"
        params.append(grammar_filter)
    sql += " ORDER BY observed_at DESC LIMIT ?"
    params.append(lim)

    rows: list[dict[str, Any]] = []
    for row in conn.execute(sql, params):
        receipt = row["receipt_path"]
        sig = row["sig_path"]
        rs = str(receipt) if receipt is not None else ""
        ss = str(sig) if sig is not None else ""
        rows.append(
            {
                "grammar_name": str(row["grammar_name"]),
                "node_type": str(row["reason"] or ""),
                "action": str(row["mutation_kind"] or ""),
                "observed_at": str(row["observed_at"]),
                "receipt_path": rs,
                "sig_path": ss,
                "receipt_exists": bool(rs) and Path(rs).is_file(),
                "sig_exists": bool(ss) and Path(ss).is_file(),
            }
        )
    return rows


def _sanitize_extension(raw: str) -> tuple[str, str | None]:
    """Safe display string + optional hex of raw UTF-8 bytes for corrupt DB text."""
    try:
        clean = raw.encode("utf-8", errors="replace").decode("utf-8")
        if clean == raw:
            return clean, None
        raw_b = raw.encode("utf-8", errors="surrogatepass")
        return clean, raw_b.hex()
    except Exception:
        return repr(raw), None


def collect_unknown_extensions(
    conn: sqlite3.Connection,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    """Unknown extensions with sanitized strings for JSON."""
    if limit is None:
        sql = "SELECT extension, first_seen_at FROM unknown_extensions ORDER BY extension ASC"
        params: Sequence[Any] = ()
    else:
        sql = (
            "SELECT extension, first_seen_at FROM unknown_extensions "
            "ORDER BY extension ASC LIMIT ?"
        )
        params = (int(limit),)
    rows_out: list[dict[str, Any]] = []
    for row in conn.execute(sql, params):
        ext_raw = str(row["extension"])
        ext_clean, hex_repr = _sanitize_extension(ext_raw)
        item: dict[str, Any] = {
            "ext": ext_clean,
            "first_seen_at": str(row["first_seen_at"]),
        }
        if hex_repr is not None:
            item["raw_bytes_hex"] = hex_repr
        rows_out.append(item)
    return rows_out


def read_llm_budget_state() -> dict[str, Any]:
    """Read in-process LLM fallback counters without importing private symbols at import time."""
    try:
        from . import llm_fallback as lf
    except Exception:
        return {
            "budget_total": None,
            "budget_remaining": None,
            "calls_today": None,
            "available": False,
        }

    try:
        total = lf._budget_from_env()  # noqa: SLF001
    except Exception:
        total = None

    remaining: int | None
    try:
        remaining = getattr(lf, "_llm_calls_remaining", None)
    except Exception:
        remaining = None

    if remaining is None:
        return {
            "budget_total": None,
            "budget_remaining": None,
            "calls_today": None,
            "available": False,
        }

    try:
        t_int = int(total) if total is not None else 0
        r_int = int(remaining)
        consumed = max(0, t_int - r_int)
    except (TypeError, ValueError):
        consumed = None

    return {
        "budget_total": int(total) if total is not None else None,
        "budget_remaining": int(remaining),
        "calls_today": consumed,
        "available": True,
    }
