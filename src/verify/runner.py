"""Orchestrate a verify run: graph signals, Hypothesis, receipt."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import inspect
import json
import os
import sys
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, TextIO

from hypothesis import given, settings, strategies as hst
from hypothesis.database import DirectoryBasedExampleDatabase, InMemoryExampleDatabase

from scan.filesystem_hygiene import (
    compute_finding,
    diff_snapshots,
    load_sandbox_config_from_env,
    merge_hygiene_into_result_entry,
    parse_bool_env,
    snapshot,
    validated_sandbox_roots,
)
from scan.turboscan.generator_inliner import maybe_substitute_hypothesis_strategy

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


def _resolve_package_path(file_path: Path) -> tuple[Path, str]:
    """Return (sys.path entry, fully qualified module name) for a source file.

    For a flat file (no ``__init__.py`` in parent), returns
    the file's parent directory and the module name equal to the file stem.
    """
    abs_path = file_path.resolve()
    parts: list[str] = [abs_path.stem]
    cur = abs_path.parent

    while (cur / "__init__.py").is_file():
        parts.insert(0, cur.name)
        cur = cur.parent

    qualified = ".".join(parts)
    return cur, qualified


def _load_target_module(file_path: Path) -> Any:
    """Import a file with package context so relative imports work.

    Restores ``sys.path`` on exit. On failure, the original exception propagates
    (not converted to None).
    """
    sys_path_entry, qualified = _resolve_package_path(file_path)
    inserted = False
    str_entry = str(sys_path_entry)
    if str_entry not in sys.path:
        sys.path.insert(0, str_entry)
        inserted = True
    try:
        if qualified in sys.modules:
            del sys.modules[qualified]
        return importlib.import_module(qualified)
    finally:
        if inserted:
            try:
                sys.path.remove(str_entry)
            except ValueError:
                pass


def _import_failure_dict(exc: Exception | None, fn_name: str) -> dict[str, Any]:
    if exc is not None:
        return {
            "input": "(import)",
            "exception_type": type(exc).__name__,
            "exception_message": (str(exc) or repr(exc))[:10_000],
            "shrunk_input": "(import)",
            "shrunk_input_size_bytes": len("(import)".encode("utf-8")),
        }
    return {
        "input": "(import)",
        "exception_type": "AttributeError",
        "exception_message": f"not found or not callable: {fn_name!r}",
        "shrunk_input": "(import)",
        "shrunk_input_size_bytes": len("(import)".encode("utf-8")),
    }


def _load_for_invariant(target: Path, name: str) -> Callable[..., Any] | None:
    try:
        m = _load_target_module(target)
    except Exception:
        return None
    o = getattr(m, name, None)
    if o is None or not callable(o):
        return None
    return o


def _import_error_receipt(
    tpath: Path,
    fsha: str,
    function: str | None,
    fn_name: str,
    ts: str,
    import_failures: list[dict[str, Any]],
    sign: bool,
    no_receipt: bool,
    receipt_dir: str | None,
    output_format: str,
    inv_pairs: int,
    lineno: int,
) -> tuple[int, str]:
    """Emit ERROR result with import failures in the receipt JSON."""
    fns_label = function or fn_name
    rbody: dict[str, Any] = {
        "version": 1,
        "kind": "verify",
        "timestamp": ts,
        "target": {
            "file": str(tpath),
            "file_sha256": fsha,
            "function": fns_label,
            "lineno": lineno,
        },
        "results": [],
        "strategies": {},
        "graph_signals": {
            "caller_count": 0,
            "boundary_examples_count": 0,
            "invariant_pairs_count": inv_pairs,
        },
        "examples_run": 0,
        "failures": import_failures,
    }
    psk = _default_secret_key()
    want_sign = sign and psk is not None and psk.is_file() and not no_receipt
    rdir = Path(receipt_dir) if receipt_dir else Path.home() / ".omnix" / "receipts"
    js2 = _json_receipt(rbody, psk, want_sign, no_receipt)
    if not no_receipt:
        nm = (function or "all")[:100].replace(os.sep, "_")
        receipt.write_receipt_to_disk(js2, function_name=nm, out_dir=rdir)  # type: ignore[assignment, call-arg, misc, call-arg, arg-type]
    if output_format == "json":
        return (int(ExitCode.ERROR), js2)
    return (int(ExitCode.ERROR), f"omnix verify: could not import {fn_name!r} from {tpath}\n")


def _strat_map(sig: list[tuple[str, str | None]], cshape: Any, bmap: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for i, (pname, hint) in enumerate(sig):
        bvals = bmap.get(i) if isinstance(bmap, dict) else []
        st = strategies.strategy_for_param(
            i, hint, cshape, list(bvals) if bvals is not None else []  # type: ignore[operator]
        )
        out[pname] = maybe_substitute_hypothesis_strategy(st)
    return out


def _hypothesis_example_database() -> DirectoryBasedExampleDatabase | InMemoryExampleDatabase | None:
    """Honor env from find_bugs / tests so Hypothesis never defaults to CWD ``.hypothesis``."""
    mem = (os.environ.get("OMNIX_HYPOTHESIS_IN_MEMORY") or "").strip().lower()
    if mem in ("1", "true", "yes"):
        return InMemoryExampleDatabase()
    raw = (os.environ.get("OMNIX_HYPOTHESIS_DATABASE_DIRECTORY") or "").strip()
    if not raw:
        return None
    try:
        base = Path(raw).expanduser().resolve()
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        return InMemoryExampleDatabase()
    return DirectoryBasedExampleDatabase(str(base))


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
    *,
    hygiene_acc: list[dict[str, Any]] | None = None,
    hygiene_ctx: dict[str, Any] | None = None,
) -> bool:
    """Run Hypothesis. Returns True if a failure was recorded (fn raised)."""
    sdict = _strat_map(params, cshape, bmap)
    tup = _tuple_strat(sdict)
    last: list = []
    hygiene_cfg = load_sandbox_config_from_env()
    hygiene_roots = validated_sandbox_roots(hygiene_cfg) if hygiene_cfg else tuple()
    delegated = parse_bool_env("OMNIX_FS_HYGIENE_DELEGATED", False)

    _db = _hypothesis_example_database()
    _kw: dict[str, Any] = {"max_examples": examples, "deadline": None}
    if _db is not None:
        _kw["database"] = _db

    @settings(**_kw)
    @given(tup)
    def _inv(t: object) -> None:  # type: ignore[no-redef, misc, union-attr, wrong-arg-count]
        args = t if isinstance(t, tuple) else (t,)  # type: ignore[assignment, misc, union-attr, arg-type]
        last.clear()
        last.append(args)  # type: ignore[operator]
        if hygiene_cfg is None or delegated:
            _invoke(fn, args)  # type: ignore[misc, call-arg, arg-type]
            return
        before = snapshot(hygiene_cfg)
        try:
            _invoke(fn, args)  # type: ignore[misc, call-arg, arg-type]
        finally:
            after = snapshot(hygiene_cfg)
            created = diff_snapshots(before, after)
            sizes: dict[str, int] = {}
            for c in created:
                pt = Path(c)
                try:
                    sizes[c] = int(pt.stat().st_size) if pt.is_file() else 0
                except OSError:
                    sizes[c] = 0
            mod = getattr(fn, "__module__", "?")
            fq = getattr(fn, "__qualname__", _fn_name)
            target_function = f"{mod}:{fq}"
            repro = os.environ.get(
                "OMNIX_FS_HYGIENE_REPRO_CMD",
                "python -m verify.cli <target> --function <name> --json --no-receipt",
            )
            hf = compute_finding(
                created_abs_paths=created,
                path_sizes=sizes,
                sandbox_roots=hygiene_roots,
                repo_root=hygiene_cfg.repo_root,
                tmp_root=hygiene_cfg.resolved_tmp_root(),
                target_function=target_function,
                fuzz_inputs=repr(args),
                reproduction=repro,
            )
            if (
                hf is not None
                and hygiene_acc is not None
                and len(hygiene_acc) < 12
            ):
                hdict = hf.as_finding_dict()
                if hygiene_ctx:
                    hdict = merge_hygiene_into_result_entry(
                        hdict,
                        file_relp=str(hygiene_ctx.get("file_relp") or ""),
                        function_name=str(hygiene_ctx.get("function_name") or _fn_name),
                        lineno=int(hygiene_ctx.get("lineno") or 0),
                    )
                hygiene_acc.append(hdict)

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


def _invariant_smoke(
    tpath: Path, pair: tuple[str, str], scope: set[str]
) -> bool:
    f1, f2 = pair
    a = _load_for_invariant(tpath, f1)
    b2 = _load_for_invariant(tpath, f2)
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
    workspace_dir: str | None = None,
) -> tuple[int, str]:
    tpath = Path(target_path).resolve()
    if not tpath.is_file() or tpath.suffix != ".py":
        return (int(ExitCode.ERROR), f"not a .py file: {tpath}\n")

    old_cwd: str | None = None
    if workspace_dir and str(workspace_dir).strip():
        try:
            wd = Path(workspace_dir).expanduser().resolve()
            wd.mkdir(parents=True, exist_ok=True)
            old_cwd = os.getcwd()
            os.chdir(wd)
        except OSError:
            old_cwd = None

    try:
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
        try:
            _file_relp = str(tpath.resolve().relative_to(Path(croot).resolve()))
        except ValueError:
            _file_relp = tpath.name
        for s in sigs:
            fn_name = s["name"]
            try:
                _mod = _load_target_module(tpath)
            except Exception as e:
                return _import_error_receipt(
                    tpath,
                    fsha,
                    function,
                    fn_name,
                    ts,
                    [_import_failure_dict(e, fn_name)],
                    sign,
                    no_receipt,
                    receipt_dir,
                    output_format,
                    len(ipairs),
                    int(s.get("lineno") or 0),
                )
            fn = getattr(_mod, fn_name, None)
            if fn is None or not callable(fn):
                return _import_error_receipt(
                    tpath,
                    fsha,
                    function,
                    fn_name,
                    ts,
                    [_import_failure_dict(None, fn_name)],
                    sign,
                    no_receipt,
                    receipt_dir,
                    output_format,
                    len(ipairs),
                    int(s.get("lineno") or 0),
                )
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
                st0 = maybe_substitute_hypothesis_strategy(st0)
                st_desc[pn] = str(st0)[:500]
            fl: list[dict[str, Any]] = []
            hygiene_acc: list[dict[str, Any]] = []
            if not params:
                # Zero-arity: no parameter space for PBT; do not invoke (avoids script entrypoints).
                pass
            else:
                _pbt(
                    tpath,
                    fn,
                    fn_name,
                    params,
                    cshape,
                    bmap,
                    examples,
                    fl,
                    hygiene_acc=hygiene_acc,
                    hygiene_ctx={
                        "file_relp": _file_relp,
                        "lineno": int(s.get("lineno") or 0),
                        "function_name": fn_name,
                    },
                )
            all_fail.extend(fl)
            r_one: dict[str, Any] = {
                "name": fn_name,
                "lineno": s.get("lineno"),
                "params": [list(t) for t in s["params"]],
                "return_hint": s.get("return_hint"),
                "strategies": st_desc,
                "failures": fl,
                "filesystem_hygiene_findings": list(hygiene_acc),
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
            if not params:
                r_one["status"] = "skipped_zero_arity"
                r_one["reason"] = "PBT requires at least one parameter"
            results.append(r_one)
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
        glob_hygiene: list[dict[str, Any]] = []
        for r in results:
            gh = r.get("filesystem_hygiene_findings") or []
            if isinstance(gh, list):
                glob_hygiene.extend(x for x in gh if isinstance(x, dict))
        ok = not all_fail and not glob_hygiene
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
            "filesystem_hygiene_findings": glob_hygiene,
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
            try:
                receipt.write_receipt_to_disk(js2, function_name=nm, out_dir=rdir)  # type: ignore[assignment, call-arg, misc, call-arg, arg-type]
            except PermissionError:
                pass
        if output_format == "json":
            return (int(ExitCode.OK) if ok else int(ExitCode.FAIL), js2)
        return (int(ExitCode.OK) if ok else int(ExitCode.FAIL), text_out)
    finally:
        if old_cwd is not None:
            try:
                os.chdir(old_cwd)
            except OSError:
                pass