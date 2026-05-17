"""`omnix grammar` subcommands (list, status, receipts, verify)."""

from __future__ import annotations

import argparse
import json
import pkgutil
import sys
import time
from pathlib import Path

_ECODE = 0
_EERR = 2


def _installed_tree_sitter_langs() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in pkgutil.iter_modules():
        n = m.name
        if not n.startswith("tree_sitter_"):
            continue
        suf = n[len("tree_sitter_"):]
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


def cmd_status(
    grammar_db: str | None,
    *,
    status_json: bool = False,
    grammar_filter: str | None = None,
) -> int:
    """Per-codebase grammar health (read-only). Delegates to :mod:`omnix.parser.cli`."""
    from omnix.parser.cli import run_grammar_status

    return run_grammar_status(
        db=grammar_db,
        as_json=status_json,
        grammar_filter=grammar_filter,
    )


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
    from omnix.receipts import keystore
    from omnix.receipts import verify as vfy

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
        return cmd_status(
            getattr(args, "grammar_db", None),
            status_json=bool(getattr(args, "status_json", False)),
            grammar_filter=getattr(args, "grammar_filter", None),
        )
    if sub == "receipts":
        return cmd_receipts()
    if sub == "verify":
        r = getattr(args, "receipt", None) or ""
        if not r:
            print("grammar verify: need receipt path", file=sys.stderr)
            return 1
        return cmd_verify(r, pub_path=getattr(args, "pubkey", None))
    return _EERR
