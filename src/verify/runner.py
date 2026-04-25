"""Orchestrate a verify run: graph signals, Hypothesis, receipt."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import importlib.util
import json
import os
import sys
import uuid
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, TextIO

from hypothesis import given, settings, strategies as hst

from . import boundary, caller_shape, invariants, receipt, signature, strategies


class ExitCode(IntEnum):
    OK = 0
    FAIL = 1
    ERROR = 2


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 16), b""):
            h.update(b)
    return h.hexdigest()


def _load(target: Path, name: str) -> Callable[..., Any] | None:
    try:
        mname = f"omnx_{name}_{uuid.uuid4().hex[:5]}"
        sp = importlib.util.spec_from_file_location(mname, str(target))
        if not sp or not sp.loader:
            return None
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        o = getattr(m, name, None)
        if o is None or not callable(o):
            return None
        return o
    except (OSError, ImportError, SyntaxError, Exception):
        return None


def _strat_map(sig: list[tuple[str, str | None]], cshape: Any, bmap: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for i, (pname, hint) in enumerate(sig):
        bvals = bmap.get(i) if isinstance(bmap, dict) else []
        st = strategies.strategy_for_param(
            i, hint, cshape, list(bvals) if bvals is not None else []  # type: ignore[operator]
        )
        out[pname] = st
    return out


def _tuple_strat(
    sdict: dict[str, Any]
) -> Any:
    if not sdict:
        return hst.tuples()  # type: ignore[call-overload, misc]
    keys = list(sdict)
    tps: list = [sdict[k] for k in keys if k in sdict]
    return hst.tuples(*tps)  # type: ignore[return-value, arg-type, call-overload]


def _invoke(fn: Callable[..., Any], t: tuple) -> object:
    if inspect.iscoroutinefunction(fn):
        return asyncio.run(fn(*t))
    return fn(*t)


def _pbt(
    _target: Path,
    fn: Callable[..., Any],
    _fn_name: str,
    params: list[tuple[str, str | None]],
    cshape: Any,
    bmap: dict[int, list[Any]],
    examples: int,
    failures: list[dict[str, Any]],
) -> bool:
    """Run Hypothesis. Returns True if a failure was recorded (fn raised)."""
    sdict = _strat_map(params, cshape, bmap)
    tup = _tuple_strat(sdict)
    last: list = []

    @settings(max_examples=examples, deadline=None)
    @given(tup)
    def _inv(t: object) -> None:  # type: ignore[no-redef, misc, union-attr, wrong-arg-count]
        args = t if isinstance(t, tuple) else (t,)  # type: ignore[assignment, misc, union-attr, arg-type]
        last.clear()
        last.append(args)  # type: ignore[operator]
        _invoke(fn, args)  # type: ignore[misc, call-arg, arg-type]

    try:
        _inv()  # type: ignore[call-arg, misc, operator, arg-type]
    except Exception as e:  # noqa: BLE001
        args = last[0] if last else ()  # type: ignore[assignment, misc, index, operator, index]
        sr = repr(args)  # type: ignore[assignment, misc, index, operator, index]
        failures.append(
            {
                "input": sr,
                "exception_type": type(e).__name__,
                "exception_message": str(e) or repr(e)[:10_000],
                "shrunk_input": sr,
                "shrunk_input_size_bytes": len(sr.encode("utf-8", errors="replace")),
            }
        )
        return True
    return False


def _run_zero_arity(
    fn: Callable[..., Any], examples: int, failures: list[dict[str, Any]]
) -> bool:
    for _i in range(examples):
        try:
            _invoke(fn, ())
        except Exception as e:  # noqa: BLE001
            failures.append(
                {
                    "input": "()",
                    "exception_type": type(e).__name__,
                    "exception_message": str(e) or repr(e)[:10_000],
                    "shrunk_input": "()",
                    "shrunk_input_size_bytes": 2,
                }
            )
            return True
    return False


def _invariant_smoke(
    tpath: Path, pair: tuple[str, str], scope: set[str]
) -> bool:
    f1, f2 = pair
    a = _load(tpath, f1)
    b2 = _load(tpath, f2)
    if a is None or b2 is None:
        return False
    s = hst.integers()
    for i in range(5):
        try:
            if hasattr(s, "example"):
                x = s.example()  # type: ignore[operator, call-arg, union-attr, misc, arg-type, attr-defined]
            else:
                x = 0
        except (Exception,):
            x = i
        try:
            mid = _invoke(a, (x,))
            _invoke(b2, (mid,))
        except Exception:  # noqa: BLE001
            return True
    return False


def _resolve_graph(
    graph_db_path: str | None, omnix_root: Path
) -> str | None:
    if os.environ.get("OMNIX_GRAPH_DB"):
        p = Path(os.environ["OMNIX_GRAPH_DB"]).resolve()
        return str(p) if p.is_file() else None
    if graph_db_path:
        p = Path(graph_db_path).resolve()
        return str(p) if p.is_file() else None
    cands = [
        omnix_root / "omnix.db",
        Path.home() / ".omnix" / "omnix.db",
        Path.home() / ".omnix" / "graph.db",
    ]
    for c in cands:
        if c.is_file():
            return str(c)
    return None


def _omnix_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _default_secret_key() -> Path | None:
    p = receipt._key_path()
    return p if p.is_file() else None


def _json_receipt(
    rbody: dict[str, Any], key: Path | None, sign: bool, no_receipt: bool
) -> str:
    b = {k: v for k, v in rbody.items() if k != "axiom_signature"}
    if not sign or no_receipt or key is None or not key.is_file():
        b2 = {**b, "axiom_signature": None}
        return json.dumps(b2, sort_keys=True, separators=(",", ":"), ensure_ascii=False)  # noqa: E501
    return receipt.mint_signed_receipt(
        b,
        secret_pem_path=key,  # type: ignore[call-overload, assignment, call-arg, misc, arg-type]
    )


def run(
    target_path: str,
    function: str | None = None,
    examples: int = 200,
    sign: bool = True,
    output_format: str = "text",
    graph_db_path: str | None = None,
    codebase_root: str | None = None,
    no_receipt: bool = False,
    receipt_dir: str | None = None,
    omnix_root: str | None = None,
) -> tuple[int, str]:
    tpath = Path(target_path).resolve()
    if not tpath.is_file() or tpath.suffix != ".py":
        return (int(ExitCode.ERROR), f"not a .py file: {tpath}\n")

    roots = Path(omnix_root).resolve() if omnix_root else _omnix_root()
    croot = Path(codebase_root).resolve() if codebase_root else roots
    gpath = _resolve_graph(graph_db_path, roots)
    if not gpath:
        return (
            int(ExitCode.ERROR),
            "omnix verify: no graph database (run: python3 omnix.py analyze <codebase> first)\n",
        )
    invariants.clear_invariant_cache()
    fsha = _sha256_file(tpath)
    sigs = signature.extract_signatures(tpath, function)
    if not sigs:
        return (
            int(ExitCode.ERROR),
            f"omnix verify: no matching function in {tpath}\n",
        )
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    all_fail: list[dict[str, Any]] = []
    inv_fail = False
    names_in_file = invariants.function_names_in_file(tpath)
    ipairs = invariants.detect_invariant_pairs_in_file(
        tpath, allowed_names=names_in_file, file_scope_path=tpath
    )
    for pr in ipairs:
        if _invariant_smoke(tpath, pr, names_in_file):
            inv_fail = True
    results: list[dict[str, Any]] = []
    for s in sigs:
        fn_name = s["name"]
        fn = _load(tpath, fn_name)
        if fn is None:
            return (int(ExitCode.ERROR), f"omnix verify: could not import {fn_name!r} from {tpath}\n")
        params: list[tuple[str, str | None]] = list(s["params"])
        cshape = caller_shape.aggregate_caller_arg_types(
            gpath, str(tpath), fn_name, str(croot)
        )
        sites = caller_shape.collect_literal_boundary_sites(
            gpath, str(tpath), fn_name, str(croot)
        )
        merged = boundary.aggregate_boundaries(sites) if sites else {}
        bmap = boundary.filter_frequent_literals(merged, min_distinct_callers=2) if merged else {}
        st_desc: dict[str, str] = {}
        for i, (pn, h) in enumerate(params):
            st0 = strategies.strategy_for_param(
                i, h, cshape, list(bmap.get(i, []))  # type: ignore[arg-type, call-overload, operator, argument]
            )
            st_desc[pn] = str(st0)[:500]
        fl: list[dict[str, Any]] = []
        if not params:
            _run_zero_arity(fn, examples, fl)
        else:
            _pbt(
                tpath, fn, fn_name, params, cshape, bmap, examples, fl
            )
        all_fail.extend(fl)
        results.append(
            {
                "name": fn_name,
                "lineno": s.get("lineno"),
                "params": [list(t) for t in s["params"]],
                "return_hint": s.get("return_hint"),
                "strategies": st_desc,
                "failures": fl,
                "graph_signals": {
                    "caller_count": sum(
                        sum(d.values()) for d in cshape.values()  # type: ignore[call-overload, iterator, item, operator, arg-type, attribute]
                    )
                    if cshape
                    else 0,
                    "boundary_examples_count": sum(
                        len(v) for v in bmap.values()  # type: ignore[call-overload, item, arg-type, attribute]
                    )
                    if bmap
                    else 0,
                    "invariant_pairs_count": len(ipairs),
                },
            }
        )
    if inv_fail:
        all_fail.append(
            {
                "input": "(invariant)",
                "exception_type": "InvariantPair",
                "exception_message": "round-trip smoke check failed",
                "shrunk_input": "(invariant)",
                "shrunk_input_size_bytes": 11,
            }
        )
    ok = not all_fail
    rdir = Path(receipt_dir) if receipt_dir else Path.home() / ".omnix" / "receipts"
    fns_one = [str(x["name"]) for x in results]  # type: ignore[assignment, misc, index, attribute]
    rbody: dict[str, Any] = {
        "version": 1,
        "kind": "verify",
        "timestamp": ts,
        "target": {
            "file": str(tpath),
            "file_sha256": fsha,
            "function": function or ",".join(fns_one),
            "lineno": sigs[0].get("lineno", 0) if sigs else 0,
        },
        "results": results,
        "strategies": {s["name"]: s["strategies"] for s in results},  # type: ignore[index, assignment, misc, attribute, index]
        "graph_signals": results[0]["graph_signals"]  # type: ignore[index, assignment, misc, attribute, index, index]
        if results
        else {
            "caller_count": 0,
            "boundary_examples_count": 0,
            "invariant_pairs_count": len(ipairs),
        },
        "examples_run": examples * max(len(sigs), 1),
        "failures": all_fail,
    }
    out_txt: list[str] = [
        f"omnix verify {tpath} ({'OK' if ok else 'FAIL'})",
    ]
    for s in results:
        out_txt.append(
            f"  {s['name']}: {len(s.get('failures', []))} failure(s) "
        )
    text_out = "\n".join(out_txt) + "\n"
    psk = _default_secret_key()
    want_sign = sign and psk is not None and psk.is_file() and not no_receipt
    js2 = _json_receipt(rbody, psk, want_sign, no_receipt)
    if not no_receipt:
        nm = (function or "all")[:100].replace(os.sep, "_")
        receipt.write_receipt_to_disk(js2, function_name=nm, out_dir=rdir)  # type: ignore[assignment, call-arg, misc, call-arg, arg-type]
    if output_format == "json":
        return (int(ExitCode.OK) if ok else int(ExitCode.FAIL), js2)
    return (int(ExitCode.OK) if ok else int(ExitCode.FAIL), text_out)