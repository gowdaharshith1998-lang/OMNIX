"""
Grammar query-pattern evolution (discovery, validation, decay) with ML-DSA-65 receipts.
P16: no signed receipt → no mutation that requires a receipt. P22: one BEGIN…COMMIT for SQL.
P13: evolution JSON is metadata only (no source code).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omnix.axiom import keystore, sign
from omnix.parser.quality_profiles import load_profile

_LOG = logging.getLogger("omnix.parser.evolution")

TIER_TOPLEVEL = "toplevel"
ADDED_AUTO = "auto_learned"
BUILTIN = "builtin_hint"  # reserved for P21; decay SQL filters added_by=auto only
ADDED_LLM = "llm_inferred"
ADDED_UNKNOWN = "unknown"  # v1 receipts on disk had no top-level added_by
RECEIPT_SCHEMA_V2 = 2
RECEIPT_SCHEMA_V3 = 3
_FORBID_MUTATION_ON_BUILTIN = frozenset(
    {"decay", "decay_pattern", "tier_change"}
)

SECRET_KEY = Path.home() / ".omnix" / "keys" / "secret.pem"
PUB_KEY = Path.home() / ".omnix" / "keys" / "public.pem"
_DEFAULT_RD = Path.home() / ".omnix" / "receipts"
_TEST_RDIR: Path | None = None
_TEST_SEC: Path | None = None
_RUN: list[Observation] = []
_PENDING_EXT: list[str] = []


@dataclass(frozen=True)
class Observation:
    grammar: str
    quality: float
    top_level_types: frozenset[str]
    known_union: frozenset[str]
    parse_mode: str = "generic"

    @property
    def unknowns(self) -> set[str]:
        return set(self.top_level_types) - set(self.known_union)


def set_evolution_test_paths(
    *, receipt_dir: Path | None = None, secret_pem: Path | None = None
) -> None:
    global _TEST_RDIR, _TEST_SEC
    _TEST_RDIR = receipt_dir
    _TEST_SEC = secret_pem


def reset_evolution_test_paths() -> None:
    global _TEST_RDIR, _TEST_SEC
    _TEST_RDIR = None
    _TEST_SEC = None


def _rdir() -> Path:
    return _TEST_RDIR or _DEFAULT_RD


def _sec() -> Path:
    return _TEST_SEC or SECRET_KEY


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def begin_evolution_run() -> None:
    _RUN.clear()
    _PENDING_EXT.clear()


def observe_parse(
    grammar: str,
    quality: float,
    top_level_node_types: set[str] | frozenset[str],
    known_type_union: set[str] | frozenset[str],
    *,
    parse_mode: str = "generic",
) -> None:
    _RUN.append(
        Observation(
            grammar=grammar,
            quality=float(quality),
            top_level_types=frozenset(top_level_node_types),
            known_union=frozenset(known_type_union),
            parse_mode=parse_mode,
        )
    )


def queue_unknown_extension(raw_ext: str) -> None:
    e = (raw_ext or "?").lstrip().lower() if raw_ext else "?"
    e = e if e.startswith(".") else f".{e}" if e != "?" else e
    _PENDING_EXT.append(e)


def record_unknown_extension(conn: sqlite3.Connection, ext: str) -> None:
    e = (ext or "?").lstrip().lower() if ext else "?"
    e = e if e.startswith(".") or e == "?" else f".{e}"
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO unknown_extensions (extension, first_seen_at) VALUES (?, ?)",
        (e, _iso_utc()),
    )
    conn.commit()


def _fingerprint() -> str:
    s = _sec()
    p = s.parent / "public.pem" if s.is_file() else PUB_KEY
    if not p.is_file():
        return ""
    return hashlib.sha256(keystore.public_from_pem(p.read_text(encoding="ascii"))).hexdigest()


def _json_canonical(b: dict[str, Any]) -> bytes:
    return json.dumps(
        b, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def resolved_added_by_from_receipt(data: dict[str, Any]) -> str:
    """v1: missing top-level added_by is treated as unknown; v2+ includes added_by when present."""
    if not isinstance(data, dict):
        return ADDED_UNKNOWN
    raw = data.get("added_by")
    if raw is not None and str(raw).strip() != "":
        return str(raw)
    if int(data.get("schema_version") or 0) < 2:
        return ADDED_UNKNOWN
    return ADDED_UNKNOWN


def resolved_quality_formula_version_from_receipt(data: dict[str, Any]) -> int:
    """
    Legacy (schema v1 and v2) evolution receipts predate *quality_formula_version*;
    all such receipts implied formula **v1** (language-agnostic :func:`compute_score`).
    Schema v3+ stores the explicit ``quality_formula_version`` (1=legacy, 2=per-grammar).
    """
    if not isinstance(data, dict):
        return 1
    if int(data.get("schema_version") or 0) < RECEIPT_SCHEMA_V3:
        return 1
    v = data.get("quality_formula_version", 1)
    try:
        return int(v)
    except (TypeError, ValueError):
        return 1


def _enrich_grammar_evolution_receipt_v3(b: dict[str, Any]) -> None:
    """Set ``schema_version`` 3 and quality-profile metadata; v3 is strict on missing keys."""
    b["schema_version"] = RECEIPT_SCHEMA_V3
    gkey = str(b.get("grammar") or "").strip() or "generic"
    p = load_profile(gkey)
    if p is None:
        raise ValueError(
            "no quality profile for evolution receipt (expected generic.json or "
            f"a profile for grammar={gkey!r})"
        )
    if b.get("quality_formula_version") is None:
        b["quality_formula_version"] = 2
    if b.get("profile_grammar") is None or str(b.get("profile_grammar", "")).strip() == "":
        b["profile_grammar"] = p.grammar
    if b.get("profile_version") is None:
        b["profile_version"] = int(p.profile_version)
    if b.get("quality_formula_version") is None:
        raise ValueError("grammar evolution receipt v3 requires 'quality_formula_version'")
    if not str(b.get("profile_grammar", "")).strip():
        raise ValueError("grammar evolution receipt v3 requires 'profile_grammar'")
    if b.get("profile_version") is None:
        raise ValueError("grammar evolution receipt v3 requires 'profile_version'")


def emit_evolution_receipt(
    body: dict[str, Any]
) -> tuple[Path, Path] | None:
    """
    Sign and write evolution JSON. Current schema is **v3** (v1/v2 on disk are still
    verifiable with ML-DSA-65). P21: refuse ``builtin_hint`` with decay / tier change.
    """
    b: dict[str, Any] = {**body}
    if b.get("kind") == "grammar_evolution":
        mut = str(b.get("mutation") or "")
        if b.get("added_by") == BUILTIN and mut in _FORBID_MUTATION_ON_BUILTIN:
            raise ValueError(
                "evolution receipt refused: builtin patterns are immutable (P21); "
                f"cannot emit mutation={mut!r} for added_by=builtin_hint"
            )
        _enrich_grammar_evolution_receipt_v3(b)
    w = _write_evolution_receipt(b)
    return w


def emit_evolution_receipt_for_test(
    added_by: str = ADDED_AUTO,
    *,
    grammar: str = "synth_test",
    quality_formula_version: int = 2,
) -> Path:
    b: dict[str, Any] = {
        "kind": "grammar_evolution",
        "grammar": grammar,
        "mutation": "synthetic",
        "observed_at": _iso_utc(),
        "added_by": added_by,
        "quality_formula_version": quality_formula_version,
    }
    out = emit_evolution_receipt(b)
    if not out:
        raise RuntimeError("emit_evolution_receipt_for_test: signing failed (key missing or invalid)")
    return out[0]


def _write_evolution_receipt(
    body: dict[str, Any]
) -> tuple[Path, Path] | None:
    skp = _sec()
    if not skp.is_file():
        return None
    try:
        sk = keystore.secret_from_pem(skp.read_text(encoding="ascii"))
    except (OSError, ValueError) as e:
        _LOG.warning("evolution: read secret: %s", e)
        return None
    tflat = _iso_utc().replace(":", "-").replace(".", "-")
    g = str(body.get("grammar", "g"))[:48]
    pdir = _rdir()
    pdir.mkdir(parents=True, exist_ok=True)
    jpath = pdir / f"evolution_{tflat}_{g}.json"
    b = {**body, "key_fp": _fingerprint()}
    raw = _json_canonical(b)
    try:
        sigb = sign.sign_bytes(sk, raw, b"", secrets.token_bytes(32))
    except ValueError as e:
        _LOG.warning("evolution: sign: %s", e)
        return None
    tmpj = pdir / f".e_{jpath.name}.j"
    tmps = pdir / f".e_{jpath.name}.s"
    # Parallel to `omnix axiom verify R.json R.sig` (not R.json.sig)
    spath = jpath.parent / f"{jpath.stem}.sig"
    tmpj.write_bytes(raw)
    tmps.write_text(keystore.signature_to_pem(sigb), encoding="ascii")
    tmpj.replace(jpath)
    tmps.replace(spath)
    return jpath, spath


def finalize_evolution_run(conn: sqlite3.Connection) -> int:
    global _RUN
    obs = list(_RUN)
    c = conn.cursor()
    n_mut = 0

    if os.environ.get("OMNIX_TEST_EVOL_FAIL") == "1":
        c.execute("BEGIN")
        c.execute(
            "INSERT INTO pattern_mutation(grammar_name, mutation_kind, pattern_id, reason, "
            "observed_at, receipt_path, sig_path) VALUES(?,?,?,?,?,?,?)",
            ("_x_", "t", None, "f", _iso_utc(), "a", "b"),
        )
        c.execute("ROLLBACK")
        _RUN.clear()
        _PENDING_EXT.clear()
        return 0

    c.execute("BEGIN")

    t0 = _iso_utc()
    for e in _PENDING_EXT:
        c.execute(
            "INSERT OR IGNORE INTO unknown_extensions (extension, first_seen_at) VALUES (?, ?)",  # noqa: E501
            (e, t0),
        )
    if _PENDING_EXT:
        _PENDING_EXT.clear()
    for o in obs:
        row = c.execute(
            "SELECT * FROM grammar_profile WHERE grammar_name=?",
            (o.grammar,),
        ).fetchone()
        if row is None:
            c.execute(
                "INSERT INTO grammar_profile(grammar_name, first_seen_at, total_files_parsed, "
                "total_quality_score) VALUES (?, ?, 1, ?)",
                (o.grammar, t0, o.quality),
            )
        else:
            c.execute(
                "UPDATE grammar_profile SET total_files_parsed = total_files_parsed + 1, "
                "total_quality_score = total_quality_score + ? WHERE grammar_name = ?",
                (o.quality, o.grammar),
            )
    ttag = _iso_utc()
    for o in obs:
        for u in o.unknowns:
            c.execute(
                """
                INSERT OR IGNORE INTO query_pattern
                (id, grammar_name, node_type, role, hit_count, miss_count, is_active, added_at, added_by)
                VALUES (null, ?, ?, ?, 0, 0, 1, ?, ?)
                """,
                (o.grammar, u, TIER_TOPLEVEL, ttag, ADDED_AUTO),
            )

    prof = {
        str(x[0]): (int(x[2]), float(x[3]))
        for x in c.execute("SELECT grammar_name, first_seen_at, total_files_parsed, total_quality_score "
                           "FROM grammar_profile")
    }

    for g in sorted({o.grammar for o in obs}):
        tf = prof.get(g, (0, 0.0))[0]
        if tf < 10:
            continue
        cands = c.execute(
            "SELECT * FROM query_pattern WHERE grammar_name=? AND hit_count=0 AND miss_count=0 AND "
            "is_active=1 AND added_by=?",
            (g, ADDED_AUTO),
        ).fetchall()
        for r in cands:
            if isinstance(r, sqlite3.Row):
                pid = int(r["id"])
                nty = str(r["node_type"])
                ab = str(r["added_by"] or ADDED_UNKNOWN)
            else:
                continue
            wq = [x.quality for x in obs if x.grammar == g and nty in x.top_level_types]
            wout = [x.quality for x in obs if x.grammar == g and nty not in x.top_level_types]
            if not wq or not wout:
                continue
            a, b0 = sum(wq) / len(wq), sum(wout) / len(wout)
            if a - b0 < 0.1:
                continue
            mbody: dict[str, Any] = {
                "kind": "grammar_evolution",
                "grammar": g,
                "mutation": "promote_pattern",
                "node_type": nty,
                "evidence": {"m_with": a, "m_wo": b0, "n_files_grammar": tf},
                "observed_at": _iso_utc(),
                "added_by": ab,
            }
            w = emit_evolution_receipt(mbody)
            if w is None:
                _LOG.warning("evolution: promote skipped (no key) grammar=%s", g)
                continue
            jp, sp = w
            c.execute("UPDATE query_pattern SET hit_count = 1 WHERE id=?", (pid,))
            c.execute(
                "INSERT INTO pattern_mutation(grammar_name, mutation_kind, pattern_id, reason, "
                "observed_at, receipt_path, sig_path) VALUES(?,?,?,?,?,?,?)",
                (g, "promote_pattern", pid, "delta", _iso_utc(), str(jp), str(sp)),
            )
            n_mut += 1

    decr = c.execute("SELECT * FROM query_pattern WHERE is_active=1 AND added_by=?", (ADDED_AUTO,)).fetchall()  # noqa: E501
    for r in decr:
        h, mi, pid = int(r[4]), int(r[5]), int(r[0])
        g = str(r[1])
        nty = str(r[2])
        ab = str(r["added_by"] or ADDED_UNKNOWN) if isinstance(r, sqlite3.Row) else ADDED_UNKNOWN
        toti = h + mi
        if toti < 20:
            continue
        p = h / toti
        if p >= 0.3:
            continue
        w = emit_evolution_receipt(
            {
                "kind": "grammar_evolution",
                "grammar": g,
                "mutation": "decay_pattern",
                "node_type": nty,
                "evidence": {"precision": p, "n": toti},
                "observed_at": _iso_utc(),
                "added_by": ab,
            }
        )
        if w is None:
            _LOG.warning("evolution: decay skipped (no key) id=%s", pid)
            continue
        jp, sp = w
        c.execute("UPDATE query_pattern SET is_active=0 WHERE id=?", (pid,))
        c.execute(
            "INSERT INTO pattern_mutation(grammar_name, mutation_kind, pattern_id, reason, "
            "observed_at, receipt_path, sig_path) VALUES(?,?,?,?,?,?,?)",
            (g, "decay", pid, "pr", _iso_utc(), str(jp), str(sp)),
        )
        n_mut += 1

    c.execute("COMMIT")
    _RUN.clear()
    return n_mut


def _emit_mutation_receipt_for_test() -> str:
    p = emit_evolution_receipt(
        {
            "kind": "grammar_evolution",
            "grammar": "synth_test",
            "mutation": "synthetic",
            "observed_at": _iso_utc(),
            "added_by": ADDED_AUTO,
        }
    )
    return str(p[0]) if p else ""
