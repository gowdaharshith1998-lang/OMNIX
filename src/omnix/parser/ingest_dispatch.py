"""Single-file graph ingest with evolution observation; uses universal.py (P11: no dedicated-parser edits)."""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from collections.abc import Iterator
from concurrent.futures import (
    FIRST_COMPLETED,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    as_completed,
    wait,
)
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tree_sitter import Language

from omnix.find_bugs.walker import iter_dispatch_paths
from omnix.graph.store import GraphStore
from omnix.omnix_version import __version__ as OMNIX_APP_VERSION
from omnix.parser import evolution
from omnix.parser.grammar_detect import detect_for_path
from omnix.parser.hint_loader import MergedHints, load_merged_hints
from omnix.parser.memory_graph import MemoryGraphStore
from omnix.parser.quality import compute_score_v2, quality_inputs_from_parsed_stats
from omnix.parser.skip_tracking import SkipAggregate
from omnix.parser.tree_parse_cache import get_shared_parser, parse_tree_cached
from omnix.parser.universal import ingest_universal_to_store, parse_stats_for_universal_ingest

_LOG = logging.getLogger("omnix.parser.ingest_dispatch")
_CACHE_SKIP = "__omnix_cache_skip__"
SCHEMA_V = "3"

_DEFAULT_MODE = "generic"

# Test hook: last ProcessPoolExecutor max_workers (set when parallel ingest runs).
_LAST_PROCESS_POOL_MAX_WORKERS: int | None = None

_BATCH_SIZE = 100
_MAX_IN_FLIGHT = 200


def default_parse_mode() -> str:
    return os.environ.get("OMNIX_PARSE_MODE", _DEFAULT_MODE).strip() or _DEFAULT_MODE


def _ingest_worker_count() -> int:
    raw = os.environ.get("OMNIX_INGEST_WORKERS", "").strip()
    if raw:
        try:
            w = int(raw, 10)
        except ValueError:
            w = max(1, (os.cpu_count() or 2) - 1)
    else:
        w = max(1, (os.cpu_count() or 2) - 1)
    return max(1, min(w, 12))


def _set_last_pool_max_workers(n: int) -> None:
    global _LAST_PROCESS_POOL_MAX_WORKERS
    _LAST_PROCESS_POOL_MAX_WORKERS = n


def _quality_grammar(grammar: str, full: Path, is_tsx: bool) -> str:
    """
    Per-file profile key. JavaScript/TSX share the TS grammar in Tree-sitter but
    :file:`javascript.json` is used for ``.js``/``.mjs``/``.cjs`` when the grammar
    name is still ``typescript``.
    """
    if grammar == "typescript" and not is_tsx:
        ext = full.suffix.lower()
        if ext in (".js", ".mjs", ".cjs"):
            return "javascript"
    return grammar


def _known_union(m: MergedHints) -> frozenset[str]:
    return frozenset(
        m.all_function_node_types
        | m.all_class_node_types
        | m.all_call_node_types
        | m.all_import_node_types
    )


def top_level_syntactic_types(
    language: Language | None,
    text: str,
    *,
    file_key: str,
    grammar_name: str,
    is_tsx: bool,
) -> set[str]:
    if not language or not text or not file_key:
        return set()
    try:
        src = text.encode("utf-8")
        g = f"ts{'x' if is_tsx else ''}" if grammar_name == "typescript" else grammar_name
        p = get_shared_parser(g, language)
        t = parse_tree_cached(g, file_key, p, src)
        rnode = t.root_node
        return {c.type for c in rnode.children if c is not None}
    except (OSError, ValueError, RuntimeError) as e:
        _LOG.debug("top_level_syntactic_types: %s", e)
        return set()


@dataclass
class IngestTotals:
    by_grammar: dict[str, int] = field(default_factory=dict)
    skipped_unknown: int = 0
    skipped_no_grammar: int = 0
    errors: int = 0
    cached: int = 0
    skip: SkipAggregate = field(default_factory=SkipAggregate)


def quality_profile_fingerprint() -> str:
    """SHA-256 over sorted ``src/omnix/parser/quality_profiles/*.json`` (bytes + name order)."""
    pdir = Path(__file__).resolve().parent / "quality_profiles"
    acc = bytearray()
    for fp in sorted(pdir.glob("*.json")):
        acc += fp.name.encode() + b"\0"
        acc += fp.read_bytes() + b"\0"
    return hashlib.sha256(bytes(acc)).hexdigest()


def _file_digest(absolute: Path, root: Path) -> tuple[str, str, float] | None:
    """(rel, sha256_hex, mtime) or None if unreadable."""
    try:
        rel = absolute.relative_to(root).as_posix()
        b = absolute.read_bytes()
        mtime = absolute.stat().st_mtime
        h = hashlib.sha256(b).hexdigest()
        return (rel, h, mtime)
    except (OSError, ValueError):
        return None


def _digest_path_list(paths: list[Path], root: Path) -> dict[str, tuple[str, float]]:
    out: dict[str, tuple[str, float]] = {}
    n_workers = min(12, max(1, (os.cpu_count() or 2) * 2))
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        futs = {ex.submit(_file_digest, p, root): p for p in paths}
        for fut in as_completed(futs):
            got = fut.result()
            if got is None:
                continue
            rel, h, mt = got
            out[rel] = (h, mt)
    return out


def _maybe_invalidate_ingest_cache(
    store: GraphStore, *, force: bool, new_profile_fp: str, omnix_version: str
) -> None:
    if force:
        print(
            "OMNIX: --force set, re-parsing all source files and rebuilding graph",
            file=sys.stderr,
        )
        store.full_invalidate_ingest_cache()
        return
    c = store.sqlite_connection()
    n_graph = int(c.execute("SELECT COUNT(*) FROM nodes").fetchone()[0] or 0)
    n_fh = int(c.execute("SELECT COUNT(*) FROM file_hashes").fetchone()[0] or 0)
    old_v = store.get_meta("omnix_version")
    old_p = store.get_meta("profile_hash")
    if n_graph > 0 and n_fh == 0:
        print(
            "OMNIX: no file hash cache in database for existing graph, "
            "re-parsing all source files (one-time cost after cache upgrade)",
            file=sys.stderr,
        )
        store.full_invalidate_ingest_cache()
        return
    if old_v and old_v != omnix_version:
        print(
            f"OMNIX: upgraded from {old_v!r} to {omnix_version!r}, "
            "re-parsing all source files (one-time cost on first run after upgrade)",
            file=sys.stderr,
        )
        store.full_invalidate_ingest_cache()
        return
    if n_graph > 0 and not old_p and n_fh > 0:
        print(
            "OMNIX: quality profile hash missing in database, re-parsing all files",
            file=sys.stderr,
        )
        store.full_invalidate_ingest_cache()
        return
    if n_graph > 0 and old_p and old_p != new_profile_fp:
        print(
            "OMNIX: quality profiles updated since last analyze, re-parsing all files "
            "(one-time cost on first run after upgrade)",
            file=sys.stderr,
        )
        store.full_invalidate_ingest_cache()
        return


def ingest_one_path_parse_only(
    job: tuple,
) -> dict[str, Any]:
    """
    Pure parse in a worker process (no GraphStore / evolution / skip_summary).
    *job* is ``(order_idx, root, full_path, parse_mode)`` or a 5-tuple with
    *test_force_basename* (from the parent) for unit tests, or 6-tuple
    *cache skip* (unchanged on-disk vs ``file_hashes``; main process only).
    """
    if len(job) == 6 and job[5] == _CACHE_SKIP:
        order_idx, root_s, full_s, _parse_mode_s, _test_force, _x = job
        root = Path(root_s)
        full = Path(full_s)
        try:
            rel = full.relative_to(root).as_posix()
        except ValueError as e:
            return {
                "order_idx": order_idx,
                "status": "error",
                "skip_reason": None,
                "parse_error": str(e),
                "rel_path": "",
            }
        return {
            "order_idx": order_idx,
            "status": "ok",
            "kind": "unchanged",
            "rel_path": rel,
        }
    if len(job) == 4:
        order_idx, root_s, full_s, parse_mode_s = job
        test_force = os.environ.get("OMNIX_TEST_FORCE_PARSE_ERROR_BASENAME")
    else:
        order_idx, root_s, full_s, parse_mode_s, test_force = job
    root = Path(root_s)
    full = Path(full_s)
    pm = parse_mode_s.strip() or _DEFAULT_MODE
    try:
        rel = full.relative_to(root).as_posix()
    except ValueError as e:
        return {
            "order_idx": order_idx,
            "status": "error",
            "skip_reason": None,
            "parse_error": str(e),
            "rel_path": "",
        }

    force_bad = (str(test_force or "")).strip() or None
    if force_bad and full.name == force_bad:
        return {
            "order_idx": order_idx,
            "status": "error",
            "skip_reason": "parse_error",
            "parse_error": "OMNIX_TEST_FORCE_PARSE_ERROR_BASENAME",
            "rel_path": rel,
        }

    try:
        st = full.stat()
    except OSError as e:
        return {
            "order_idx": order_idx,
            "status": "error",
            "skip_reason": None,
            "parse_error": str(e),
            "rel_path": rel,
        }

    ext_key = full.suffix.lower() or "(no extension)"
    d = detect_for_path(full)
    if d.skip_reason == "unknown_extension":
        return {
            "order_idx": order_idx,
            "status": "skip",
            "skip_reason": "unknown_extension",
            "parse_error": None,
            "rel_path": rel,
            "ext_key": ext_key,
            "st_size": st.st_size,
            "evolution_queue": full.suffix or "?",
        }
    if d.skip_reason == "no_grammar":
        return {
            "order_idx": order_idx,
            "status": "skip",
            "skip_reason": "no_grammar",
            "parse_error": None,
            "rel_path": rel,
            "ext_key": ext_key,
            "st_size": st.st_size,
            "grammar_suggest": d.grammar_name,
        }
    if not d.language or not d.inferred_lang:
        return {
            "order_idx": order_idx,
            "status": "skip",
            "skip_reason": "no_grammar",
            "parse_error": None,
            "rel_path": rel,
            "ext_key": ext_key,
            "st_size": st.st_size,
            "grammar_suggest": d.grammar_name,
        }

    try:
        with full.open("rb") as bf:
            probe = bf.read(8192)
    except OSError as e:
        return {
            "order_idx": order_idx,
            "status": "error",
            "skip_reason": None,
            "parse_error": str(e),
            "rel_path": rel,
        }
    if b"\x00" in probe:
        return {
            "order_idx": order_idx,
            "status": "skip",
            "skip_reason": "binary",
            "parse_error": None,
            "rel_path": rel,
            "ext_key": ext_key,
            "st_size": st.st_size,
        }

    try:
        text = full.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {
            "order_idx": order_idx,
            "status": "error",
            "skip_reason": None,
            "parse_error": str(e),
            "rel_path": rel,
        }

    m0 = load_merged_hints(d.inferred_lang, parse_mode=pm)
    if not text.strip():
        return {
            "order_idx": order_idx,
            "status": "ok",
            "kind": "empty",
            "rel_path": rel,
            "text": text,
            "grammar_name": d.grammar_name,
            "inferred_lang": d.inferred_lang,
            "is_tsx": d.is_tsx,
            "known_union": sorted(_known_union(m0)),
            "parse_mode": m0.parse_mode,
        }

    mem = MemoryGraphStore()
    lang = d.language
    m = m0
    try:
        ingest_universal_to_store(
            mem,
            rel,
            text,
            d.inferred_lang,
            lang,
            parse_mode=pm,
            merged_hints=m,
            is_tsx=d.is_tsx,
        )
    except (OSError, ValueError, RuntimeError) as e:
        return {
            "order_idx": order_idx,
            "status": "error",
            "skip_reason": "parse_error",
            "parse_error": str(e),
            "rel_path": rel,
            "ext_key": ext_key,
            "st_size": st.st_size,
        }

    snap = mem.to_transfer_dicts()
    n_snap = len(snap.get("nodes", []))
    e_snap = len(snap.get("edges", []))
    qgram = _quality_grammar(d.grammar_name, full, d.is_tsx)
    stats = parse_stats_for_universal_ingest(
        mem, rel, text, grammar=d.grammar_name, language=lang, is_tsx=d.is_tsx
    )
    q = compute_score_v2(quality_inputs_from_parsed_stats(stats), qgram)
    types = top_level_syntactic_types(
        lang,
        text,
        file_key=rel,
        grammar_name=d.grammar_name,
        is_tsx=d.is_tsx,
    )
    return {
        "order_idx": order_idx,
        "status": "ok",
        "kind": "graph",
        "rel_path": rel,
        "text": text,
        "parse_result": snap,
        "n_snap_nodes": n_snap,
        "n_snap_edges": e_snap,
        "grammar_name": d.grammar_name,
        "inferred_lang": d.inferred_lang,
        "is_tsx": d.is_tsx,
        "q": q,
        "types": sorted(types),
        "known_union": sorted(_known_union(m0)),
        "parse_mode": m0.parse_mode,
    }


def _purge_stale_ingest_entry(store: GraphStore, rel: str) -> None:
    """If *rel* was previously recorded in ``file_hashes``, remove graph and cache row."""
    if not rel or not store.get_file_hash_row(rel):
        return
    store.delete_graph_rows_for_file_path(rel)
    store.delete_file_hash(rel)


def _apply_result_row(
    r: dict[str, Any],
    store: GraphStore,
    root: Path,
    tot: IngestTotals | None,
    agg: SkipAggregate | None,
    *,
    n_batch: list[int],
    file_digests: dict[str, tuple[str, float]] | None = None,
) -> None:
    """
    *n_batch* is a single-element list used as a mutable int counter for
    files imported since last commit_batch (0..BATCH-1).
    When *tot* is None (e.g. ``ingest_one_path`` for evolution), callers
    update totals; *agg* may be None to skip ``skip_summary`` recording.
    """
    st = r.get("status")
    if st == "skip":
        _purge_stale_ingest_entry(store, str(r.get("rel_path") or ""))
        reason = r["skip_reason"]
        ext_key = r.get("ext_key") or "(no extension)"
        if tot is not None:
            if reason == "unknown_extension":
                evolution.queue_unknown_extension(r.get("evolution_queue") or "?")
                tot.skipped_unknown += 1
            elif reason == "no_grammar":
                evolution.queue_unknown_extension("?")
                tot.skipped_no_grammar += 1
        else:
            if reason == "unknown_extension":
                evolution.queue_unknown_extension(r.get("evolution_queue") or "?")
            elif reason == "no_grammar":
                evolution.queue_unknown_extension("?")
        if agg is not None:
            agg.record_skip(ext_key, reason, int(r.get("st_size", 0)))
        return
    if st == "error":
        _purge_stale_ingest_entry(store, str(r.get("rel_path") or ""))
        if tot is not None:
            tot.errors += 1
        is_parse = r.get("skip_reason") == "parse_error" or r.get("parse_error")
        if is_parse and agg is not None:
            ext_key = (
                r.get("ext_key")
                or (Path(r.get("rel_path", "x")).suffix.lower() or "(no extension)")
            )
            agg.record_skip(
                str(ext_key),
                "parse_error",
                int(r.get("st_size", 0) or 1),
            )
        return

    if st != "ok":
        return

    if r.get("kind") == "unchanged":
        if tot is not None:
            tot.cached += 1
        return

    if r.get("kind") == "empty":
        ku = _known_union(
            load_merged_hints(r["inferred_lang"], parse_mode=r["parse_mode"])
        )
        evolution.observe_parse(
            r["grammar_name"],
            0.0,
            set(),
            ku,
            parse_mode=r["parse_mode"],
        )
        if agg is not None:
            agg.add_parsed(r.get("text") or "")
        if tot is not None:
            g = r["grammar_name"] or "?"
            tot.by_grammar[g] = tot.by_grammar.get(g, 0) + 1
        rel0 = r["rel_path"]
        if file_digests and rel0 in file_digests:
            s0, m0t = file_digests[rel0]
            store.set_file_hash(rel0, s0, m0t, node_count=0, edge_count=0)
        return

    if r.get("kind") == "graph":
        rel = r["rel_path"]
        text = r["text"]
        full = root / rel
        d = detect_for_path(full)
        if not d.language:
            if tot is not None:
                tot.errors += 1
            return
        if n_batch[0] == 0:
            store.begin_batch()
        store.delete_graph_rows_for_file_path(rel)
        pr = r["parse_result"] or {"nodes": [], "edges": []}
        store.import_graph_snapshot(pr.get("nodes", []), pr.get("edges", []))
        n_batch[0] += 1
        if n_batch[0] >= _BATCH_SIZE:
            store.commit_batch()
            n_batch[0] = 0

        lang = d.language
        qgram = _quality_grammar(d.grammar_name, full, d.is_tsx)
        stats = parse_stats_for_universal_ingest(
            store, rel, text, grammar=d.grammar_name, language=lang, is_tsx=d.is_tsx
        )
        _ = compute_score_v2(quality_inputs_from_parsed_stats(stats), qgram)
        evolution.observe_parse(
            r["grammar_name"],
            float(r["q"]),
            set(r.get("types") or []),
            frozenset(r.get("known_union") or []),
            parse_mode=r["parse_mode"],
        )
        if agg is not None:
            agg.add_parsed(text)
        if tot is not None:
            g = r["grammar_name"] or "?"
            tot.by_grammar[g] = tot.by_grammar.get(g, 0) + 1
        if file_digests and rel in file_digests:
            s0, m0t = file_digests[rel]
            nn = int(r.get("n_snap_nodes", 0) or 0)
            en = int(r.get("n_snap_edges", 0) or 0)
            store.set_file_hash(rel, s0, m0t, node_count=nn, edge_count=en)
        return


def ingest_one_path(
    store: GraphStore,
    root: Path,
    full: Path,
    *,
    parse_mode: str | None = None,
    skip_tracker: SkipAggregate | None = None,
) -> tuple[str | None, str | None]:
    """
    Ingest a single file and call ``observe_parse``. Returns
    ``(status_token, grammar_name_on_success)`` where *status_token* is
    ``None`` on success, else a skip/error label. Does not call
    ``evolution.begin_evolution_run``. Does not commit; caller should commit
    (``commit`` or ``commit_batch``) as appropriate.
    """
    tf = os.environ.get("OMNIX_TEST_FORCE_PARSE_ERROR_BASENAME")
    job = (0, str(root), str(full), parse_mode or default_parse_mode(), tf)
    r = ingest_one_path_parse_only(job)
    n_batch: list[int] = [0]
    _apply_result_row(
        r,
        store,
        root,
        None,
        skip_tracker,
        n_batch=n_batch,
        file_digests=None,
    )
    if n_batch[0] > 0:
        store.commit_batch()
    if r.get("status") == "ok" and r.get("kind") in ("empty", "graph"):
        return (None, r.get("grammar_name"))
    if r.get("status") == "skip":
        t = r.get("skip_reason")
        if t == "unknown_extension":
            return ("unknown_extension", None)
        if t == "no_grammar":
            return ("no_grammar", None)
        if t == "binary":
            return ("binary", None)
    if r.get("status") == "error":
        return ("error", None)
    return ("error", None)


def _future_to_result(
    f: Any,
    j: int,
    paths: list[Path],
    r: Path,
) -> dict[str, Any]:
    try:
        ex_c = f.exception()
        if ex_c is not None:
            return {
                "order_idx": j,
                "status": "error",
                "skip_reason": "parse_error",
                "parse_error": str(ex_c),
                "rel_path": str(paths[j].relative_to(r)),
            }
        return f.result()
    except (BrokenProcessPool, RuntimeError) as exn:
        _LOG.warning("ingest: future error: %s", exn)
        return {
            "order_idx": j,
            "status": "error",
            "skip_reason": "parse_error",
            "parse_error": str(exn),
            "rel_path": str(paths[j].relative_to(r)),
        }


def _iter_parse_results_in_order(
    r: Path,
    paths: list[Path],
    jobs: list[tuple],
) -> Iterator[dict[str, Any]]:
    """
    Yield parse results in **walk order** (submission index) so the main
    process can apply them while new futures still run. Uses a reorder buffer
    and ``wait(FIRST_COMPLETED)`` + sliding window submit (``_MAX_IN_FLIGHT``).
    """
    n = len(jobs)
    if n == 0:
        return
    workers = _ingest_worker_count()
    if workers == 1:
        for j in jobs:
            yield ingest_one_path_parse_only(j)
        return

    results: list[dict[str, Any] | None] = [None] * n
    next_sub = 0
    next_emit = 0
    inflight: dict[Any, int] = {}
    ex: ProcessPoolExecutor | None = None
    try:
        ex = ProcessPoolExecutor(max_workers=workers)
        _set_last_pool_max_workers(workers)
        while next_emit < n:
            while next_sub < n and len(inflight) < _MAX_IN_FLIGHT and ex is not None:
                fut = ex.submit(ingest_one_path_parse_only, jobs[next_sub])
                inflight[fut] = next_sub
                next_sub += 1
            while next_emit < n and results[next_emit] is not None:
                row = results[next_emit]
                assert row is not None
                next_emit += 1
                yield row
            if next_emit >= n:
                break
            if inflight:
                done, _ = wait(
                    set(inflight), return_when=FIRST_COMPLETED, timeout=3600.0
                )
                for f in done:
                    j = inflight.pop(f)
                    results[j] = _future_to_result(f, j, paths, r)
            elif next_sub < n and ex is not None:
                continue
            else:
                break
    except BrokenProcessPool as b2:
        _LOG.warning("ingest: pool broken, sequential fallback: %s", b2)
        if ex is not None:
            ex.shutdown(wait=True)
        ex = None
        for k in range(n):
            if results[k] is None:
                try:
                    results[k] = ingest_one_path_parse_only(jobs[k])
                except (OSError, ValueError, RuntimeError) as e2:
                    results[k] = {
                        "order_idx": k,
                        "status": "error",
                        "skip_reason": "parse_error",
                        "parse_error": str(e2),
                        "rel_path": str(paths[k].relative_to(r)),
                    }
    finally:
        if ex is not None:
            ex.shutdown(wait=True)
    for idx in range(n):
        if results[idx] is None:
            try:
                results[idx] = ingest_one_path_parse_only(jobs[idx])
            except (OSError, ValueError, RuntimeError) as e2:
                results[idx] = {
                    "order_idx": idx,
                    "status": "error",
                    "skip_reason": "parse_error",
                    "parse_error": str(e2),
                    "rel_path": str(paths[idx].relative_to(r)),
                }
    while next_emit < n:
        row = results[next_emit]
        assert row is not None
        next_emit += 1
        yield row


def _run_ingest_parallel(
    store: GraphStore,
    r: Path,
    paths: list[Path],
    parse_mode: str | None,
    tot: IngestTotals,
    *,
    file_digests: dict[str, tuple[str, float]] | None = None,
    use_cache: set[int] | None = None,
) -> None:
    pm = parse_mode if parse_mode is not None else default_parse_mode()
    n_batch: list[int] = [0]
    test_force = os.environ.get("OMNIX_TEST_FORCE_PARSE_ERROR_BASENAME")
    ucache = use_cache or set()
    jobs: list[tuple[Any, ...]] = []
    for i, full in enumerate(paths):
        t = (i, str(r), str(full), pm, test_force)
        if i in ucache:
            t = t + (_CACHE_SKIP,)
        jobs.append(t)
    n = len(jobs)
    if n == 0:
        return
    for row in _iter_parse_results_in_order(r, paths, jobs):
        _apply_result_row(
            row,
            store,
            r,
            tot,
            tot.skip,
            n_batch=n_batch,
            file_digests=file_digests,
        )
    if n_batch[0] > 0:
        store.commit_batch()


def _resolve_cross_file_calls(store: GraphStore, root: Path) -> int:
    """Second pass: resolve CALLS edges *across* files.

    Each file is parsed by a worker into its own isolated ``MemoryGraphStore``,
    so the per-file call index only ever contains that one file's definitions
    and cross-module calls never form an edge — the program graph the product
    is built around was silently single-file for call relationships.

    After every file's definitions are merged into ``store`` we rebuild a
    GLOBAL call index and re-run the language call pass against it. This is
    additive and safe:
      * ``add_edge`` dedups, so within-file edges already present are skipped;
      * ``_resolve_callee`` prefers a same-file definition, so a correct
        within-file resolution is never changed — only genuinely cross-file
        calls gain the edge they were missing.

    Currently covers the languages with dedicated, name-resolving parsers
    (Python, TypeScript/TSX); other languages keep their existing behavior.
    Returns the number of files re-resolved (for stats/telemetry).
    """
    from omnix.parser import python_parser as pp
    from omnix.parser import typescript_parser as tp
    from omnix.parser import universal as up

    py_files: list[str] = []
    ts_files: list[tuple[str, bool]] = []
    rust_files: list[str] = []
    for node in list(store.iter_all_nodes()):
        if node.type != "file":
            continue
        lang = (node.metadata or {}).get("language")
        rel = node.file_path
        if not rel:
            continue
        if lang == "python":
            py_files.append(rel)
        elif lang in ("typescript", "tsx"):
            ts_files.append((rel, lang == "tsx"))
        elif lang == "rust":
            rust_files.append(rel)

    def _read(rel: str) -> str | None:
        try:
            return (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    resolved = 0
    if py_files:
        py_idx = pp._build_call_index(store)  # type: ignore[attr-defined]
        for rel in py_files:
            text = _read(rel)
            if text is None:
                continue
            try:
                pp._pass2_calls(store, rel, text, py_idx)  # type: ignore[attr-defined]
                resolved += 1
            except (OSError, ValueError, RuntimeError):
                _LOG.warning("cross-file call resolution failed for %s", rel)
    if ts_files:
        ts_idx = tp._build_ts_call_index(store)  # type: ignore[attr-defined]
        for rel, is_tsx in ts_files:
            text = _read(rel)
            if text is None:
                continue
            try:
                tp._ts_pass2(store, rel, text, is_tsx, ts_idx)  # type: ignore[attr-defined]
                resolved += 1
            except (OSError, ValueError, RuntimeError):
                _LOG.warning("cross-file call resolution failed for %s", rel)
    if rust_files:
        from omnix.parser.grammar_detect import try_load_language_for_grammar
        from omnix.parser.hint_loader import load_merged_hints

        rust_lang = try_load_language_for_grammar("rust")
        if rust_lang is not None:
            rust_idx = up._build_rust_call_index(store)  # type: ignore[attr-defined]
            m_rust = load_merged_hints("rust", parse_mode="hinted")
            for rel in rust_files:
                text = _read(rel)
                if text is None:
                    continue
                try:
                    up._rust_resolve_calls_from_text(  # type: ignore[attr-defined]
                        store, rel, text, rust_lang, m_rust, rust_idx
                    )
                    resolved += 1
                except (OSError, ValueError, RuntimeError):
                    _LOG.warning("cross-file call resolution failed for %s", rel)
    return resolved


def ingest_unified_codebase(
    target_root: str,
    store: GraphStore,
    *,
    parse_mode: str | None = None,
    force: bool = False,
    omnix_version: str = OMNIX_APP_VERSION,
) -> IngestTotals:
    """Full-tree ingest + observation for ``omnix analyze`` (optional Merkle cache)."""
    r = Path(target_root).resolve()
    tot = IngestTotals()
    agg = tot.skip
    fp = quality_profile_fingerprint()
    _maybe_invalidate_ingest_cache(
        store, force=force, new_profile_fp=fp, omnix_version=omnix_version
    )
    paths = list(iter_dispatch_paths(r, skip_tracker=agg))
    walked = {p.relative_to(r).as_posix() for p in paths}
    for pth in list(store.all_file_hash_paths()):
        if pth not in walked:
            store.delete_graph_rows_for_file_path(pth)
            store.delete_file_hash(pth)
    file_digests = _digest_path_list(paths, r)
    ucache: set[int] = set()
    if not force:
        for i, full in enumerate(paths):
            rel = full.relative_to(r).as_posix()
            d = file_digests.get(rel)
            if not d:
                continue
            row = store.get_file_hash_row(rel)
            if not row:
                continue
            h0, m0, _lp, _nn, _en = row
            if h0 == d[0] and abs(float(m0) - d[1]) < 1e-9:
                ucache.add(i)
    _run_ingest_parallel(
        store,
        r,
        paths,
        parse_mode,
        tot,
        file_digests=file_digests,
        use_cache=ucache,
    )
    # Resolve CALLS edges across files (the per-file workers can only resolve
    # within a single file's isolated store).
    _resolve_cross_file_calls(store, r)
    agg.persist(store)
    store.set_meta("omnix_version", omnix_version)
    store.set_meta("profile_hash", fp)
    store.set_meta("schema_version", SCHEMA_V)
    store.commit()
    return tot


def run_evolution_ingest_on_store(
    store: GraphStore,
    root: Path,
    max_size: int,
    *,
    parse_mode: str | None = None,
) -> IngestTotals:
    """Re-ingest a codebase for evolution (``find-bugs``); keep *store* open for ``finalize``."""
    tot = IngestTotals()
    for full in iter_dispatch_paths(root, max_size=max_size):
        t, gname = ingest_one_path(store, root, full, parse_mode=parse_mode)
        try:
            store.commit()
        except (OSError, ValueError):
            _LOG.warning("evolution ingest commit failed for %s", full)
        if t is None:
            g = gname or "?"
            tot.by_grammar[g] = tot.by_grammar.get(g, 0) + 1
        elif t == "unknown_extension":
            tot.skipped_unknown += 1
        elif t == "no_grammar":
            tot.skipped_no_grammar += 1
        elif t == "binary":
            pass
        else:
            tot.errors += 1
    return tot
