"""Orchestrate a whole-codebase ``find_bugs`` scan (graph, PBT, bundle)."""

from __future__ import annotations

import json
import os
import pwd
from dataclasses import asdict
import getpass
import resource
import signal
import sqlite3
import subprocess
import sys
import time
import traceback
from collections import Counter
from collections.abc import Iterable
from multiprocessing import get_context
from pathlib import Path
from typing import Any, cast

from verify import runner as verify_runner
from verify.signature import extract_signatures

from . import bundle as bundle_mod
from .entry_points import (
    detect_entry_points,
    detect_framework_decorated,
    graph_id_for,
)
from .severity import compute_severity, rank_findings
from .walker import scan_codebase_sources

VERIFY_TIMEOUT_S = 30.0
DEFAULT_MAX_RSS_PER_VERIFY = 512 * 1024 * 1024  # 512 MB
MAX_RSS_PER_VERIFY = int(
    os.environ.get("OMNIX_FIND_BUGS_RSS_CAP_BYTES", str(DEFAULT_MAX_RSS_PER_VERIFY))
)


def _max_rss_per_verify() -> int:
    raw = os.environ.get("OMNIX_FIND_BUGS_RSS_CAP_BYTES")
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            return MAX_RSS_PER_VERIFY
    return MAX_RSS_PER_VERIFY


def _set_subprocess_limits() -> None:
    # Address-space cap (best-effort RSS ceiling) so pathological allocations
    # raise MemoryError inside the worker instead of kernel OOM-killing us.
    cap = _max_rss_per_verify()
    resource.setrlimit(
        resource.RLIMIT_AS, (cap, cap)
    )


def _verify_subprocess_cmd(run_args: dict[str, Any]) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "verify.cli",
        str(run_args["target_path"]),
        "--examples",
        str(int(run_args["examples"])),
        "--json",
        "--no-receipt",
    ]
    fn = run_args.get("function")
    if fn:
        cmd.extend(["--function", str(fn)])
    gdb = run_args.get("graph_db_path")
    if gdb:
        cmd.extend(["--graph-db", str(gdb)])
    croot = run_args.get("codebase_root")
    if croot:
        cmd.extend(["--codebase-root", str(croot)])
    return cmd


def _omnix_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _real_home_dir() -> str:
    """Home directory independent of $HOME (needed for subprocess site-packages)."""
    try:
        return pwd.getpwuid(os.getuid()).pw_dir
    except Exception:
        u = (
            os.environ.get("SUDO_USER")
            or os.environ.get("USER")
            or os.environ.get("LOGNAME")
            or ""
        )
        if not u:
            try:
                u = getpass.getuser()
            except Exception:
                u = ""
        cand = Path("/home") / u if u else None
        if cand and cand.is_dir():
            return str(cand)
        return "/"


def ensure_find_bugs_graph_db(
    codebase: Path, explicit: str | None = None
) -> tuple[Path | None, str | None]:
    """Open or create the graph SQLite file for find-bugs (Q2: per-codebase, no home fallback)."""
    import logging

    from src.graph.store import GraphStore

    _log = logging.getLogger("omnix.find_bugs")

    def _open_or_bootstrap(p: Path) -> tuple[Path | None, str | None]:
        p = p.resolve()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:  # pragma: no cover — exercised via readonly test
            return (None, f"cannot create graph database at {p} ({e})")
        try:
            st = GraphStore(str(p))
            st.close()
        except (OSError, ValueError, sqlite3.OperationalError) as e:
            return (None, f"cannot create graph database at {p} ({e})")
        return (p, None)

    if explicit and str(explicit).strip():
        p0 = Path(explicit).expanduser()
        if p0.is_file():
            return (p0.resolve(), None)
        r, e = _open_or_bootstrap(p0)
        return (r, e)
    ev = (os.environ.get("OMNIX_GRAPH_DB") or "").strip()
    if ev:
        p1 = Path(ev).expanduser()
        if p1.is_file():
            return (p1.resolve(), None)
        return _open_or_bootstrap(p1)
    c1 = (codebase / "omnix.db").resolve()
    if c1.is_file():
        return (c1, None)
    r, e = _open_or_bootstrap(c1)
    if e is None and r is not None:
        _log.info("ℹ Created per-codebase DB at %s", r)
    return (r, e)


def _relpos(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _lang_for_layer6(p: Path) -> str:
    s = p.suffix.lower()
    if s in (".rs",):
        return "rust"
    if s in (".go",):
        return "go"
    if s in (".java", ".kt", ".kts"):
        return "java"
    if s in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".c", ".h", ".cpp", ".hpp", ".cc", ".cs"):
        return "typescript" if s in (".ts", ".tsx", ".js", ".jsx", ".mjs") else s[1:]
    return p.suffix[1:] or "unknown"


def _iter_layer6_targets(
    gdb: Path, root: Path
) -> list[tuple[Path, str, str, int, str]]:
    """Non-``.py`` files with at least one function/method node in the graph."""
    con = sqlite3.connect(f"file:{gdb}?mode=ro", uri=True, timeout=5.0)
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT DISTINCT file_path FROM nodes "
            "WHERE file_path IS NOT NULL AND LOWER(file_path) NOT LIKE '%.py'",
        ).fetchall()
    finally:
        con.close()
    out: list[tuple[Path, str, str, int, str]] = []
    for r in rows:
        rel = str(r[0] or "")
        if not rel or rel.lower().endswith(".py"):
            continue
        p = (root / rel)
        if not p.is_file():
            continue
        con2 = sqlite3.connect(f"file:{gdb}?mode=ro", uri=True, timeout=5.0)
        try:
            con2.row_factory = sqlite3.Row
            fns = con2.execute(
                "SELECT name, start_line FROM nodes "
                "WHERE file_path = ? AND type IN ('function', 'method')",
                (rel,),
            ).fetchall()
        finally:
            con2.close()
        for row in fns:
            out.append(
                (p, rel, str(row["name"]), int(row["start_line"] or 0), _lang_for_layer6(p))
            )
    return out


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


def _child_verify_limited(out_q: object, run_args: dict[str, Any]) -> None:
    os.environ["HOME"] = _real_home_dir()
    try:
        _set_subprocess_limits()
    except Exception:
        pass
    _child_verify(out_q, run_args)


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
    """(exit_code, payload, worker_err) where verify runs in a subprocess.

    Timeout is enforced by `communicate(timeout=...)` so we can always apply
    per-process memory limits via `preexec_fn`.
    """
    env = dict(os.environ)
    # Keep caller's HOME for bundle/receipts, but run verify subprocess with the
    # *real* home so user-site deps (e.g. Hypothesis) remain importable even when
    # tests monkeypatch HOME.
    env["HOME"] = _real_home_dir()
    src_root = str((_omnix_root() / "src").resolve())
    env["PYTHONPATH"] = (
        src_root
        + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    )
    p = subprocess.Popen(
        _verify_subprocess_cmd(run_args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(_omnix_root()),
        start_new_session=True,
        preexec_fn=_set_subprocess_limits,
    )
    try:
        if os.environ.get("OMNIX_FIND_BUGS_NO_TIMEOUT") or timeout_s <= 0:
            out, err = p.communicate()
        else:
            out, err = p.communicate(timeout=float(timeout_s))
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except Exception:
            p.kill()
        _ = p.communicate(timeout=2.0)
        return (2, "", f"verify timed out after {int(timeout_s)}s")
    rc = int(p.returncode or 0)
    err_s = err.strip() if err and err.strip() else ""
    werr = err_s if (rc != 0 and not out.strip() and err_s) else (err_s if rc == 2 else None)
    if werr and "no module named" in werr.lower() and "hypothesis" in werr.lower():
        # Fallback: tests may monkeypatch HOME and hide user-site deps from
        # subprocesses. Use a spawned worker process and set limits there, so
        # the parent process can't be destabilized by RLIMIT_AS.
        ctx = get_context("spawn")
        q: Any = ctx.Queue()
        wp = ctx.Process(target=_child_verify_limited, args=(q, run_args), daemon=True)
        wp.start()
        wp.join(timeout=timeout_s if timeout_s > 0 else None)
        if wp.is_alive():
            wp.terminate()
            wp.join(3.0)
            return (2, "", f"verify timed out after {int(timeout_s)}s")
        try:
            c2, t2, w2 = q.get(block=True, timeout=0.5)
        except Exception:
            return (2, "", "no result from verify worker")
        if w2 is not None:
            return (2, "", str(w2))
        if isinstance(c2, int) and isinstance(t2, str):
            return (c2, t2, None)
        return (2, "", "invalid worker response")
    return (rc, out or "", werr)


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


def _looks_like_memory_error(txt: str | None) -> bool:
    if not txt:
        return False
    t = txt.lower()
    return "memoryerror" in t or "cannot allocate memory" in t


def _failures_for_name(j: dict[str, Any], fn: str) -> list[dict[str, Any]]:
    for r in j.get("results") or []:
        if isinstance(r, dict) and r.get("name") == fn:
            f = r.get("failures") or []
            if isinstance(f, list):
                return f  # type: ignore[return-value]
    top = j.get("failures") or []
    return top if isinstance(top, list) else []  # type: ignore[return-value]


def _layer7_python_fixable(finding: dict[str, Any]) -> bool:
    if finding.get("kind") == "memory_pathology":
        return False
    rel = str(finding.get("file", ""))
    if not rel.lower().endswith(".py"):
        return False
    lang = (finding.get("language") or "") or ""
    if str(lang) and str(lang).lower() not in ("python", "py", ""):
        return False
    return bool(finding.get("function"))


def _summary_text(
    top_n: int,
    findings: list[dict[str, Any]],
    files_scanned: int,
    fn_count: int,
    ex_total: int,
    wall: float,
    bundle_path: str | None,
    code_fix_note: str | None = None,
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
    if code_fix_note:
        lines.append(code_fix_note)
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
    enable_fix: bool = False,
) -> tuple[int, str, dict[str, Any] | None]:
    t0 = time.perf_counter()
    root = Path(codebase_path).resolve()
    if not root.is_dir():
        return (2, f"not a directory: {root}\n", None)
    oroot = str(_omnix_root())
    gdb_t, gerr = ensure_find_bugs_graph_db(root, graph_db)
    if gerr or gdb_t is None:
        return (
            2,
            (gerr or f"no graph database for {root} (set OMNIX_GRAPH_DB, or use --graph-db, or run omnix analyze; find-bugs creates <codebase>/omnix.db when the tree is writable)\n"),
            None,
        )
    gdb = gdb_t
    if not gdb.is_file():
        return (
            2,
            f"graph database path not usable: {gdb}\n",
            None,
        )
    from src.graph.store import GraphStore
    from src.parser import evolution as _evo
    from src.parser.ingest_dispatch import run_evolution_ingest_on_store

    _evo.begin_evolution_run()
    st = GraphStore(str(gdb))
    try:
        _ = run_evolution_ingest_on_store(
            st, root, max_file_size, parse_mode=None
        )
        _evo.finalize_evolution_run(st.sqlite_connection())
    finally:
        st.close()
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
        frame_skip = {n: r for n, r in detect_framework_decorated(fpath)}
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
            fwr = frame_skip.get(fn)
            if fwr is not None:
                skipped_main.append(
                    {"file": relp, "function": fn, "reason": fwr}
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
                elif _looks_like_memory_error(werr):
                    findings.append(
                        {
                            "kind": "memory_pathology",
                            "file": relp,
                            "function": fn,
                            "lineno": lineno,
                            "severity_score": 100,
                            "caller_count": in_cnt.get(graph_id_for(relp, fn), 0),
                            "reachable_from_entries": bool(
                                entry_reach_map.get(graph_id_for(relp, fn), False)
                            ),
                            "cluster_id": cc.get(graph_id_for(relp, fn)),
                            "input": "(unknown)",
                            "reason": f"function exhausted memory limit ({int(_max_rss_per_verify() / (1024 * 1024))} MB)",
                            "failures": [
                                {
                                    "shrunk_input": "(unknown)",
                                    "exception_type": "MemoryError",
                                    "message": "verify worker hit memory limit",
                                }
                            ],
                        }
                    )
                else:
                    import_errs.append(
                        {
                            "kind": "import_error",
                            "file": relp,
                            "message": f"verify worker error (function {fn!r}): {werr[:5000]}",
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
                if _looks_like_memory_error(msg):
                    findings.append(
                        {
                            "kind": "memory_pathology",
                            "file": relp,
                            "function": fn,
                            "lineno": lineno,
                            "severity_score": 100,
                            "caller_count": in_cnt.get(graph_id_for(relp, fn), 0),
                            "reachable_from_entries": bool(
                                entry_reach_map.get(graph_id_for(relp, fn), False)
                            ),
                            "cluster_id": cc.get(graph_id_for(relp, fn)),
                            "input": "(unknown)",
                            "reason": f"function exhausted memory limit ({int(_max_rss_per_verify() / (1024 * 1024))} MB)",
                            "failures": [
                                {
                                    "shrunk_input": "(unknown)",
                                    "exception_type": "MemoryError",
                                    "message": msg,
                                }
                            ],
                        }
                    )
                    continue
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
                mem_fails = [
                    x
                    for x in fails
                    if isinstance(x, dict)
                    and (
                        str(x.get("exception_type") or "") == "MemoryError"
                        or _looks_like_memory_error(str(x.get("message") or ""))
                        or _looks_like_memory_error(str(x.get("exception_message") or ""))
                    )
                ]
                if mem_fails:
                    mf0 = mem_fails[0]
                    shr = str(mf0.get("shrunk_input") or mf0.get("input") or "(unknown)")
                    findings.append(
                        {
                            "kind": "memory_pathology",
                            "file": relp,
                            "function": fn,
                            "lineno": lineno,
                            "severity_score": 100,
                            "caller_count": in_cnt.get(graph_id_for(relp, fn), 0),
                            "reachable_from_entries": bool(
                                entry_reach_map.get(graph_id_for(relp, fn), False)
                            ),
                            "cluster_id": cc.get(graph_id_for(relp, fn)),
                            "input": shr,
                            "reason": f"function exhausted memory limit ({int(_max_rss_per_verify() / (1024 * 1024))} MB)",
                            "failures": _first_three(mem_fails),
                        }
                    )
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
    if os.environ.get("OMNIX_DISABLE_LAYER6", "").lower() not in (
        "1",
        "true",
        "yes",
    ):
        from src.verify.runners import cargo_fuzz as _cargo
        from src.verify.runners import go_fuzz as _gof
        from src.verify.runners import jqwik as _jqw
        from src.verify.runners.detect import detect_universal_backend
        from src.verify.runners.subprocess_llm import run_layer6_subprocess_limited

        for abs_p, relp, fn, lineno, lang in _iter_layer6_targets(gdb, root):
            fcount += 1
            det = detect_universal_backend(root, relp, abs_p, lang)
            if det.backend == "cargo_fuzz":
                _ = _cargo.try_run_cargo_fuzz(root)
            elif det.backend == "go_fuzz":
                _ = _gof.try_run_go_fuzz(root)
            elif det.backend == "jqwik":
                _ = _jqw.try_run_jqwik(root)
            sig0 = ""
            try:
                lines0 = abs_p.read_text(encoding="utf-8", errors="replace").splitlines()  # noqa: E501, SIM115
            except OSError:  # pragma: no cover
                lines0 = []
            for ln in lines0[:3]:
                if (lang == "rust" and "fn " in ln) or (lang == "go" and "func " in ln):
                    sig0 = ln
                    break
            r6 = run_layer6_subprocess_limited(
                root, relp, lang, fn, sig0, agent_id=root.name, timeout_s=12.0
            )
            ex_total += r6.ex_total
            dmeta = {**r6.extra_metadata, "layer6_detection": asdict(det)}
            for it0 in r6.findings or []:
                ffs = it0.get("failures")
                if not isinstance(ffs, list) or not ffs:
                    continue
                sc2 = compute_severity(
                    {"file": relp, "function": fn, "failures": ffs},
                    gctx,
                )
                gfk = graph_id_for(relp, fn)
                findings.append(
                    {
                        "file": relp,
                        "function": fn,
                        "lineno": max(lineno, 1),
                        "language": lang,
                        "runner_used": r6.runner_used,
                        "metadata": dmeta,
                        "severity_score": sc2,
                        "caller_count": in_cnt.get(gfk, 0),
                        "reachable_from_entries": bool(
                            entry_reach_map.get(gfk, False)
                        ),
                        "cluster_id": cc.get(gfk),
                        "failures": _first_three(
                            ffs
                            if all(isinstance(x, dict) for x in ffs)
                            else []
                        )
                        or ffs,
                    }
                )
    wall = round(time.perf_counter() - t0, 3)
    ranked = rank_findings([dict(x) for x in findings])
    code_fix_out: str | None = None
    code_fix_detail: dict[str, Any] | None = None
    if enable_fix and ranked:
        from . import fixer

        for fd0 in ranked:
            if not _layer7_python_fixable(fd0):
                continue
            ores = fixer.orchestrate_code_fix(
                repo_root=root,
                rel_failing=str(fd0["file"]),
                function_name=str(fd0["function"]),
                language=str(fd0.get("language") or "python"),
                original_failure=dict(fd0),
                graph_db=gdb,
                agent_id=root.name,
            )
            code_fix_detail = {
                "success": ores.success,
                "message": ores.message,
                "receipt_path": ores.receipt_path,
                "body": ores.body,
            }
            rp = ores.receipt_path or "none (keys missing)"
            if ores.success:
                code_fix_out = (
                    "Code fix (sandbox, P27): a proposed change is in the signed receipt. "
                    f"Receipt: {rp}  — review and apply with git apply from the repo root."
                )
            else:
                code_fix_out = (
                    f"Code fix (sandbox) did not produce a patch: {ores.message}.  "
                    f"Receipt/audit: {rp}"
                )
            break
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
        "skipped_by_reason": dict(
            sorted(
                Counter(s.get("reason", "") for s in skipped_main if s).items()
            )
        ),
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
        if code_fix_detail is not None:
            pout["code_fix"] = code_fix_detail
        out0 = json_text if json_text.endswith("\n") else json_text + "\n"
        if code_fix_detail is not None:
            out0 += (
                json.dumps({"code_fix": code_fix_detail}, ensure_ascii=False) + "\n"
            )
        return (exitv, out0, pout)
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
            code_fix_out,
        ),
        pout,
    )
