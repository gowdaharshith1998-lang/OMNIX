"""`omnix grammar` subcommands (list, status, receipts, verify)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import pkgutil

_ECODE = 0
_EERR = 2


def _installed_tree_sitter_langs() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in pkgutil.iter_modules():
        n = m.name
        if not n.startswith("tree_sitter_"):
            continue
        suf = n[13:]
        if not suf or suf in seen:
            continue
        seen.add(suf)
        out.append({"name": f"tree_sitter_{suf}", "lang": suf})
    out.sort(key=lambda d: d["lang"])
    return out


def cmd_list() -> int:
    rows = _installed_tree_sitter_langs()
    for d in rows:
        print(f"{d['name']}\t{d['lang']}")
    if not rows:
        print("no tree_sitter_* packages found in environment", file=sys.stderr)
    return 0 if rows else 0


def _resolve_grammar_db(arg_path: str | None) -> Path:
    if arg_path:
        p = Path(arg_path).expanduser()
        if not p.is_file():
            print(f"grammar status: not a file: {p}", file=sys.stderr)
            return Path()
        return p.resolve()
    c = (Path.cwd() / "omnix.db").resolve()
    if c.is_file():
        return c
    print("grammar status: use --db PATH or run from a tree with ./omnix.db", file=sys.stderr)
    return Path()


def cmd_status(grammar_db: str | None) -> int:
    db = _resolve_grammar_db(grammar_db)
    if not db or not str(db):
        return _EERR
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5.0)
    try:
        con.row_factory = sqlite3.Row
        for row in con.execute(
            "SELECT grammar_name, total_files_parsed, total_quality_score "
            "FROM grammar_profile ORDER BY grammar_name"
        ):
            g = str(row["grammar_name"])
            tf = int(row["total_files_parsed"] or 0)
            tq = float(row["total_quality_score"] or 0.0)
            avg = (tq / tf) if tf else 0.0
            n_pat = con.execute(
                "SELECT count(*) FROM query_pattern WHERE grammar_name = ? AND is_active = 1",  # noqa: E501
                (g,),
            ).fetchone()[0]
            n_mut = con.execute(
                "SELECT count(*) FROM pattern_mutation WHERE grammar_name = ?",
                (g,),
            ).fetchone()[0]
            print(
                f"{g}\tfiles={tf}\tavg_quality={avg:.4f}\t"
                f"active_patterns={int(n_pat)}\tmutations={int(n_mut)}"
            )
    finally:
        con.close()
    return _ECODE


def cmd_receipts() -> int:
    rroot = (Path.home() / ".omnix" / "receipts").expanduser()
    if not rroot.is_dir():
        print("no receipt directory: ~/.omnix/receipts", file=sys.stderr)
        return 0
    found = sorted(rroot.glob("evolution_*.json"), key=lambda p: p.name)
    for p in found:
        t = 0.0
        st = p.stat()
        t = st.st_mtime
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
        grammar = ""
        try:
            b = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            if isinstance(b, dict):
                grammar = str(b.get("grammar", "") or b.get("grammar_name", ""))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            grammar = "?"
        print(f"{p}\t{ts}\t{grammar}")
    if not found:
        print("no evolution_*.json in ~/.omnix/receipts")
    return 0


def cmd_verify(
    receipt: str, pub_path: str | None = None
) -> int:
    jpath = Path(receipt).expanduser().resolve()
    if not jpath.is_file():
        print(f"not a file: {jpath}", file=sys.stderr)
        return 1
    spath = jpath.parent / f"{jpath.stem}.sig"
    if not spath.is_file():
        print(f"missing signature: {spath}", file=sys.stderr)
        return 1
    pdir = (Path(pub_path) if pub_path else Path.home() / ".omnix" / "keys" / "public.pem").expanduser()  # noqa: E501
    if not pdir.is_file():
        print(
            f"grammar verify: public key not found: {pdir}",
            file=sys.stderr,
        )
        return 1
    from axiom import keystore, verify as vfy

    try:
        pk = keystore.public_from_pem(pdir.read_text(encoding="ascii"))
        sig = keystore.signature_from_pem(spath.read_text(encoding="ascii"))
        msg = jpath.read_bytes()
    except OSError as e:
        print(e, file=sys.stderr)
        return 2
    if vfy.verify_bytes(pk, msg, b"", sig):
        print("Signature verified successfully")
        return 0
    print("Signature verification FAILED", file=sys.stderr)
    return 1


def run_grammar(args: argparse.Namespace) -> int:
    sub = getattr(args, "grammar_sub", None)
    if not sub:
        print("usage: omnix grammar {list,status,receipts,verify}", file=sys.stderr)
        return _EERR
    if sub == "list":
        return cmd_list()
    if sub == "status":
        return cmd_status(getattr(args, "grammar_db", None))
    if sub == "receipts":
        return cmd_receipts()
    if sub == "verify":
        r = getattr(args, "receipt", None) or ""
        if not r:
            print("grammar verify: need receipt path", file=sys.stderr)
            return 1
        return cmd_verify(r, pub_path=getattr(args, "pubkey", None))
    return _EERR
