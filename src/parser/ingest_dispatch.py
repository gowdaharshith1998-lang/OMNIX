"""Single-file graph ingest with evolution observation; uses universal.py (P11: no dedicated-parser edits)."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser

from src.graph.store import GraphStore
from src.parser import evolution
from src.find_bugs.walker import iter_dispatch_paths
from src.parser.grammar_detect import detect_for_path
from src.parser.hint_loader import MergedHints, load_merged_hints
from src.parser.memory_graph import MemoryGraphStore
from src.parser.quality import compute_score_v2, quality_inputs_from_parsed_stats
from src.parser.skip_tracking import SkipAggregate
from src.parser.universal import ingest_universal_to_store, parse_stats_for_universal_ingest

_LOG = logging.getLogger("omnix.parser.ingest_dispatch")

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


def _parser(lang: Language) -> Parser:
    return Parser(lang)


def top_level_syntactic_types(
    language: Language | None, text: str
) -> set[str]:
    if not language or not text:
        return set()
    try:
        src = text.encode("utf-8")
        pr = _parser(language).parse(src)
        rnode = pr.root_node
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
    skip: SkipAggregate = field(default_factory=SkipAggregate)


def ingest_one_path_parse_only(
    job: tuple,
) -> dict[str, Any]:
    """
    Pure parse in a worker process (no GraphStore / evolution / skip_summary).
    *job* is ``(order_idx, root, full_path, parse_mode)`` or a 5-tuple with
    *test_force_basename* (from the parent) for unit tests.
    """
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
    qgram = _quality_grammar(d.grammar_name, full, d.is_tsx)
    stats = parse_stats_for_universal_ingest(
        mem, rel, text, grammar=d.grammar_name, language=lang, is_tsx=d.is_tsx
    )
    q = compute_score_v2(quality_inputs_from_parsed_stats(stats), qgram)
    types = top_level_syntactic_types(lang, text)
    return {
        "order_idx": order_idx,
        "status": "ok",
        "kind": "graph",
        "rel_path": rel,
        "text": text,
        "parse_result": snap,
        "grammar_name": d.grammar_name,
        "inferred_lang": d.inferred_lang,
        "is_tsx": d.is_tsx,
        "q": q,
        "types": sorted(types),
        "known_union": sorted(_known_union(m0)),
        "parse_mode": m0.parse_mode,
    }


def _apply_result_row(
    r: dict[str, Any],
    store: GraphStore,
    root: Path,
    tot: IngestTotals | None,
    agg: SkipAggregate | None,
    *,
    n_batch: list[int],
) -> None:
    """
    *n_batch* is a single-element list used as a mutable int counter for
    files imported since last commit_batch (0..BATCH-1).
    When *tot* is None (e.g. ``ingest_one_path`` for evolution), callers
    update totals; *agg* may be None to skip ``skip_summary`` recording.
    """
    st = r.get("status")
    if st == "skip":
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
) -> None:
    pm = parse_mode if parse_mode is not None else default_parse_mode()
    n_batch: list[int] = [0]
    test_force = os.environ.get("OMNIX_TEST_FORCE_PARSE_ERROR_BASENAME")
    jobs = [
        (i, str(r), str(full), pm, test_force) for i, full in enumerate(paths)
    ]
    n = len(jobs)
    if n == 0:
        return
    for row in _iter_parse_results_in_order(r, paths, jobs):
        _apply_result_row(row, store, r, tot, tot.skip, n_batch=n_batch)
    if n_batch[0] > 0:
        store.commit_batch()


def ingest_unified_codebase(
    target_root: str, store: GraphStore, *, parse_mode: str | None = None
) -> IngestTotals:
    """Full-tree ingest + observation for ``omnix analyze``."""
    r = Path(target_root).resolve()
    tot = IngestTotals()
    agg = tot.skip
    paths = list(iter_dispatch_paths(r, skip_tracker=agg))
    _run_ingest_parallel(store, r, paths, parse_mode, tot)
    agg.persist(store)
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