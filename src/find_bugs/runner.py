"""Orchestrate a whole-codebase ``find_bugs`` scan (graph, PBT, bundle)."""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import time
import traceback
from collections.abc import Iterable
from multiprocessing import get_context
from pathlib import Path
from typing import Any, cast

from verify import runner as verify_runner
from verify.signature import extract_signatures

from . import bundle as bundle_mod
from .entry_points import (
    detect_entry_points,
    graph_id_for,
)
from .severity import compute_severity, rank_findings
from .walker import scan_codebase_sources

VERIFY_TIMEOUT_S = 30.0


def _omnix_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def resolve_graph_db(
    codebase: Path, explicit: str | None = None
) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return p
    envp = os.environ.get("OMNIX_GRAPH_DB")
    if envp and Path(envp).is_file():
        return Path(envp).resolve()
    c1 = (codebase / "omnix.db").resolve()
    h = (Path.home() / ".omnix" / "omnix.db").resolve()
    if c1.is_file():
        return c1
    if h.is_file():
        return h
    o = _omnix_root() / "omnix.db"
    if o.is_file():
        return o
    return None


def _relpos(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _omnix_py_path() -> Path:
    return (_omnix_root() / "omnix.py").resolve()


def _file_has_name_main_guard(fpath: Path) -> bool:
    try:
        t = fpath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return 'if __name__ == "__main__"' in t


def _skip_for_main_transparency(
    fpath: Path, fn: str
) -> str | None:
    if fpath.resolve() == _omnix_py_path():
        return "omnix_entry"
    if fn == "main" and _file_has_name_main_guard(fpath):
        return "main_block"
    return None


def _load_call_edges(db: Path) -> list[tuple[str, str]]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5.0)
    try:
        return [
            (str(s), str(t))
            for s, t in con.execute(
                "SELECT source_id, target_id FROM edges "
                "WHERE relationship = 'CALLS'"
            ).fetchall()
        ]
    finally:
        con.close()


def _inbound_caller_count(edges: list[tuple[str, str]]) -> dict[str, int]:
    c: dict[str, int] = {}
    for _s, t in edges:
        if "::" in t:
            c[t] = c.get(t, 0) + 1
    return c


def _adj_out(edges: list[tuple[str, str]]) -> dict[str, set[str]]:
    a: dict[str, set[str]] = {}
    for s, t in edges:
        if "::" not in s or "::" not in t:
            continue
        a.setdefault(s, set()).add(t)
    return a


def _undirected_cc_ids(edges: list[tuple[str, str]]) -> dict[str, int]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        p = parent.get(x, x)
        if p != x:
            p = find(p)
            parent[x] = p
        return p

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    seen: set[str] = set()
    for s, t in edges:
        if "::" not in s or "::" not in t:
            continue
        for x in (s, t):
            if x not in parent:
                parent[x] = x
                seen.add(x)
        union(s, t)
    roots: dict[str, int] = {}
    nxt = 0
    for n in sorted(seen):
        r = find(n)
        if r not in roots:
            roots[r] = nxt
            nxt += 1
    return {n: roots[find(n)] for n in seen}


def _reachable_from_entries(adj: dict[str, set[str]], entries: set[str]) -> set[str]:
    w = [e for e in entries if e and "::" in e]
    seen: set[str] = set()
    for e in w:
        seen.add(e)
    i = 0
    while i < len(w):
        u = w[i]
        i += 1
        for v in adj.get(u, ()):
            if v not in seen:
                seen.add(v)
                w.append(v)
    return seen


def all_nodes(adj: dict[str, set[str]]) -> set[str]:
    s: set[str] = set()
    for a, b in adj.items():
        s.add(a)
        s |= b
    return s


def _longest_path_depth(adj: dict[str, set[str]], entries: set[str], cap: int = 40) -> int:
    best = 0

    def dfs(u: str, stack: set[str], depth: int) -> None:
        nonlocal best
        if depth > cap or u in stack:
            return
        best = max(best, depth)
        nstack = set(stack)
        nstack.add(u)
        for v in sorted(adj.get(u, ())):
            dfs(v, nstack, depth + 1)

    for e in sorted(x for x in entries if "::" in x):
        dfs(e, set(), 1)
    return best


def _entry_point_graph_ids(
    code_root: Path, file_paths: Iterable[Path]
) -> list[str]:
    got: set[str] = set()
    for p in file_paths:
        for e in detect_entry_points(p, code_root):
            if ":" in e:
                pth, name = e.rsplit(":", 1)
                got.add(graph_id_for(pth, name))
    return sorted(got)


def _ep_display_ids(graph_fqids: list[str]) -> list[str]:
    return [f"{x.split('::', 1)[0]}:{x.split('::', 1)[1]}" for x in graph_fqids]


def _child_verify(
    out_q: object,
    run_args: dict[str, Any],
) -> None:
    try:
        c, t = verify_runner.run(
            run_args["target_path"],
            function=run_args.get("function"),
            examples=run_args["examples"],
            sign=run_args.get("sign", False),
            output_format=run_args.get("output_format", "json"),
            graph_db_path=run_args.get("graph_db_path"),
            codebase_root=run_args.get("codebase_root"),
            no_receipt=run_args.get("no_receipt", True),
            omnix_root=run_args.get("omnix_root"),
        )
        cast(Any, out_q).put((c, t, None))
    except (Exception, KeyboardInterrupt) as e:  # noqa: BLE001
        try:
            cast(Any, out_q).put(
                (2, "", f"{e!s}\n{traceback.format_exc()}")
            )
        except (BrokenPipeError, OSError):
            return


def _run_verify_direct(run_args: dict[str, Any]) -> tuple[int, str]:
    return verify_runner.run(
        run_args["target_path"],
        function=run_args.get("function"),
        examples=run_args["examples"],
        sign=run_args.get("sign", False),
        output_format=run_args.get("output_format", "json"),
        graph_db_path=run_args.get("graph_db_path"),
        codebase_root=run_args.get("codebase_root"),
        no_receipt=run_args.get("no_receipt", True),
        omnix_root=run_args.get("omnix_root"),
    )


def _run_verify_limited(
    run_args: dict[str, Any], timeout_s: float
) -> tuple[int, str, str | None]:
    """(exit_code, payload, worker_err). *timeout* uses a real-time timer in-process
    on Unix; *spawn* on platforms without itimer, or for ``OMNIX_FIND_BUGS_NO_TIMEOUT``."""
    if os.environ.get("OMNIX_FIND_BUGS_NO_TIMEOUT"):
        a = _run_verify_direct(run_args)
        return (a[0], a[1], None)
    if timeout_s <= 0:
        a = _run_verify_direct(run_args)
        return (a[0], a[1], None)
    itimer = hasattr(signal, "ITIMER_REAL") and hasattr(signal, "SIGALRM")
    if itimer:

        def _handler(_s: int, _f: Any) -> None:
            raise TimeoutError("omnix find-bugs: verify time limit")

        oldh = signal.signal(  # type: ignore[assignment, attr-defined, misc]
            signal.SIGALRM, _handler
        )
        try:
            signal.setitimer(  # type: ignore[union-attr, arg-type, attr-defined, unused-ignore, misc, operator]
                signal.ITIMER_REAL, float(timeout_s), 0.0
            )
            try:
                a = _run_verify_direct(run_args)
                return (a[0], a[1], None)
            except TimeoutError as e:
                return 2, "", str(e)
            finally:
                signal.setitimer(  # type: ignore[union-attr, arg-type, attr-defined, operator, unused-ignore, misc]
                    signal.ITIMER_REAL, 0.0, 0.0
                )
        finally:
            if oldh is not None:
                signal.signal(  # type: ignore[assignment, attr-defined, arg-type, misc, unused-ignore]
                    signal.SIGALRM, oldh
                )
    else:
        ctx = get_context("spawn")
        q: Any = ctx.Queue()
        p = ctx.Process(target=_child_verify, args=(q, run_args), daemon=True)
        p.start()
        p.join(timeout=timeout_s)
        if p.is_alive():
            p.terminate()
            p.join(3.0)
            return (2, "", f"verify timed out after {int(timeout_s)}s")
        try:
            c, t, werr = q.get(block=True, timeout=0.5)
        except (OSError, ValueError, Exception):
            c, t, werr = (2, "", "no result from verify worker")
        if werr is not None:
            return 2, "", werr
        if isinstance(c, int) and isinstance(t, str):
            return c, t, None
        return 2, "", "invalid worker response"


def _first_three(failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in failures[:3]:
        if not isinstance(f, dict):
            continue
        out.append(
            {
                "shrunk_input": f.get("shrunk_input"),
                "exception_type": f.get("exception_type"),
                "message": f.get("exception_message", ""),
            }
        )
    return out


def _failures_for_name(j: dict[str, Any], fn: str) -> list[dict[str, Any]]:
    for r in j.get("results") or []:
        if isinstance(r, dict) and r.get("name") == fn:
            f = r.get("failures") or []
            if isinstance(f, list):
                return f  # type: ignore[return-value]
    top = j.get("failures") or []
    return top if isinstance(top, list) else []  # type: ignore[return-value]


def _summary_text(
    top_n: int,
    findings: list[dict[str, Any]],
    files_scanned: int,
    fn_count: int,
    ex_total: int,
    wall: float,
    bundle_path: str | None,
) -> str:
    lines: list[str] = [
        "OMNIX Bug Finder",
        f"Scanned: {files_scanned} Python file(s), {fn_count} function(s)",
        f"Wall time: {wall:.1f}s  Examples run: {ex_total}",
    ]
    if not findings:
        lines.append("No PBT findings.")
    else:
        lines.append(
            f"! {len(findings)} finding(s) (top {min(top_n, len(findings))} shown):"
        )
        for f in rank_findings(findings)[:top_n]:
            s = f.get("severity_score", 0)
            p = f.get("file", "")
            n = f.get("function", "")
            cc = f.get("caller_count", 0)
            er = "entry-reachable" if f.get("reachable_from_entries") else "not entry-reached"
            lines.append(f"  [{s}] {p}:{n} (caller_count={cc}, {er})")
            subs = f.get("failures") or []
            if isinstance(subs, list) and subs:
                x0 = subs[0] if isinstance(subs[0], dict) else {}
                msg = x0.get("message", "")
                lines.append(f"    {x0.get('exception_type', 'Error')}: {msg!s}")
    if bundle_path:
        lines.append(f"Signed bundle: {bundle_path}")
    if findings:
        lines.append("Exit 1 (findings present).")
    else:
        lines.append("Exit 0 (no findings).")
    return "\n".join(lines) + "\n"


def run_find_bugs(
    codebase_path: str,
    examples: int = 50,
    top: int = 10,
    json_mode: bool = False,
    no_bundle: bool = False,
    include_private: bool = False,
    max_file_size: int = 1_000_000,
    graph_db: str | None = None,
    no_sign: bool = False,
) -> tuple[int, str, dict[str, Any] | None]:
    t0 = time.perf_counter()
    root = Path(codebase_path).resolve()
    if not root.is_dir():
        return (2, f"not a directory: {root}\n", None)
    oroot = str(_omnix_root())
    gdb = resolve_graph_db(root, graph_db)
    if not gdb or not gdb.is_file():
        return (
            2,
            "run omnix analyze first (graph DB missing: ~/.omnix/omnix.db or <codebase>/omnix.db)\n",
            None,
        )
    paths, n_parse_skip, n_too_big = scan_codebase_sources(
        root, max_size=max_file_size
    )
    files_scanned = len(paths)
    files_skipped = n_too_big + n_parse_skip
    fcount = 0
    e_all = _load_call_edges(gdb)
    in_cnt = _inbound_caller_count(e_all)
    adj2 = _adj_out(e_all)
    cc = _undirected_cc_ids(e_all)
    epoints: set[str] = set(_entry_point_graph_ids(root, paths))
    reach = _reachable_from_entries(adj2, epoints)
    allf = {x for x in all_nodes(adj2) if "::" in x} | {x for x in in_cnt}
    entry_reach_map: dict[str, bool] = {k: (k in reach) for k in sorted(allf)}
    n_clusters = len({v for v in cc.values()}) if cc else 0
    d_long = _longest_path_depth(adj2, epoints)
    gctx: dict[str, Any] = {
        "caller_counts": in_cnt,
        "entry_reachable": entry_reach_map,
    }
    ep_list = _ep_display_ids(sorted(epoints))
    rel_sizes: list[tuple[str, int]] = []
    for p in paths:
        try:
            st = p.stat()
            rel_sizes.append((_relpos(p, root), st.st_size))
        except OSError:
            rel_sizes.append((_relpos(p, root), 0))
    findings: list[dict[str, Any]] = []
    import_errs: list[dict[str, Any]] = []
    timeouts: list[dict[str, Any]] = []
    ex_total = 0
    gpath = str(gdb)
    croot = str(root)
    skipped_main: list[dict[str, Any]] = []
    base_run: dict[str, Any] = {
        "examples": examples,
        "sign": False,
        "output_format": "json",
        "graph_db_path": gpath,
        "codebase_root": croot,
        "no_receipt": True,
        "omnix_root": oroot,
    }
    for fpath in paths:
        relp = _relpos(fpath, root)
        try:
            sigs = extract_signatures(fpath, None)
        except (OSError, SyntaxError, ValueError) as e:
            import_errs.append(
                {
                    "kind": "import_error",
                    "file": relp,
                    "message": f"extract_signatures: {e!s}",
                }
            )
            continue
        for s in sigs:
            fn = str(s.get("name", ""))
            fcount += 1
            if not include_private and fn.startswith("_"):
                continue
            sk = _skip_for_main_transparency(fpath, fn)
            if sk:
                skipped_main.append(
                    {"file": relp, "function": fn, "reason": sk}
                )
                continue
            lineno = int(s.get("lineno", 0) or 0)
            ra = {**base_run, "target_path": str(fpath), "function": fn}
            code, out, werr = _run_verify_limited(ra, VERIFY_TIMEOUT_S)
            ex_total += examples
            wlow = (werr or "").lower()
            w_timeout = werr and (
                "time limit" in wlow
                or "timed out" in wlow
                or "verify timed out" in wlow
            )
            j: dict[str, Any] = {}
            if out and out.strip():
                try:
                    j = json.loads(out)
                except json.JSONDecodeError:
                    j = {}
            if werr:
                ex_total -= examples
                if w_timeout:
                    timeouts.append(
                        {
                            "kind": "timeout_skip",
                            "file": relp,
                            "function": fn,
                            "message": werr or "timeout",
                        }
                    )
                continue
            if code == 2:
                fl = j.get("failures")
                msg = "verify error"
                if (
                    isinstance(fl, list)
                    and fl
                    and isinstance(fl[0], dict)
                ):
                    msg = str(
                        fl[0].get("exception_message", msg)  # type: ignore[call-overload, index, union-attr]
                    )[:5000]
                import_errs.append(
                    {
                        "kind": "import_error",
                        "file": relp,
                        "message": f"{msg} (function {fn!r})",
                    }
                )
                continue
            if code == 0:
                continue
            if code == 1:
                fails: list[dict[str, Any]] = []
                rawf = _failures_for_name(j, fn) or (j.get("failures") or [])
                for x in (
                    rawf if isinstance(rawf, list) else []
                ):
                    if isinstance(x, dict):
                        fails.append(x)
                if not fails and isinstance(j.get("failures"), list):
                    for x in j["failures"] or []:
                        if isinstance(x, dict):
                            fails.append(x)
                if not fails:
                    continue
                fk = graph_id_for(relp, fn)
                sub = _first_three(fails)
                sc = compute_severity(
                    {
                        "file": relp,
                        "function": fn,
                        "failures": fails,
                    },
                    gctx,
                )
                fd0: dict[str, Any] = {
                    "file": relp,
                    "function": fn,
                    "lineno": lineno,
                    "severity_score": sc,
                    "caller_count": in_cnt.get(fk, 0),
                    "reachable_from_entries": bool(entry_reach_map.get(fk, False)),
                    "cluster_id": cc.get(fk),
                    "failures": sub,
                }
                findings.append(fd0)
    wall = round(time.perf_counter() - t0, 3)
    ranked = rank_findings([dict(x) for x in findings])
    finger = bundle_mod.codebase_fingerprint(sorted(rel_sizes))
    target_meta = {
        "codebase_path": str(root),
        "codebase_sha256": finger,
        "file_count": files_scanned,
        "function_count": fcount,
    }
    ssum: dict[str, Any] = {
        "findings_count": len(ranked),
        "files_scanned": files_scanned,
        "files_skipped": files_skipped,
        "import_errors_count": len(import_errs),
        "timeout_skips_count": len(timeouts),
        "total_examples_run": ex_total,
        "wall_time_seconds": wall,
        "skipped_main_count": len(skipped_main),
    }
    gsig: dict[str, Any] = {
        "entry_points_detected": ep_list,
        "clusters_detected": n_clusters,
        "longest_call_chain_depth": d_long,
    }
    ns = no_sign or (no_bundle and not json_mode)
    json_text = bundle_mod.assemble_and_sign(
        target_meta,
        ssum,
        ranked,
        import_errs,
        timeouts,
        gsig,
        skipped_main=skipped_main,
        no_sign=ns,
    )
    pout: dict[str, Any] | None = None
    bpath: str | None = None
    rdir = Path.home() / ".omnix" / "receipts"
    if not no_bundle:
        w = bundle_mod.write_bundle(
            json_text, rdir, codebase_name=root.name
        )
        bpath = str(w)
    exitv = 1 if ranked else 0
    if json_mode:
        pout = json.loads(json_text)
        return (exitv, json_text + "\n", pout)
    return (
        exitv,
        _summary_text(
            top,
            ranked,
            files_scanned,
            fcount,
            ex_total,
            wall,
            bpath,
        ),
        pout,
    )
