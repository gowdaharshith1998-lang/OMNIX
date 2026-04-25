"""Single-file graph ingest with evolution observation; uses universal.py (P11: no dedicated-parser edits)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Language, Parser

from src.graph.store import GraphStore
from src.parser import evolution
from src.find_bugs.walker import iter_dispatch_paths
from src.parser.grammar_detect import detect_for_path
from src.parser.hint_loader import MergedHints, load_merged_hints
from src.parser.quality import compute_score_v2, quality_inputs_from_parsed_stats
from src.parser.skip_tracking import SkipAggregate
from src.parser.universal import ingest_universal_to_store, parse_stats_for_universal_ingest

_LOG = logging.getLogger("omnix.parser.ingest_dispatch")

_DEFAULT_MODE = "generic"


def default_parse_mode() -> str:
    return os.environ.get("OMNIX_PARSE_MODE", _DEFAULT_MODE).strip() or _DEFAULT_MODE


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
        root = _parser(language).parse(src).root_node
        return {c.type for c in root.children if c is not None}
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
    ``evolution.begin_evolution_run``.
    """
    pm = parse_mode if parse_mode is not None else default_parse_mode()
    rel = full.relative_to(root).as_posix()
    try:
        st = full.stat()
    except OSError as e:
        _LOG.warning("stat %s: %s", rel, e)
        return ("error", None)

    ext_key = full.suffix.lower() or "(no extension)"
    d = detect_for_path(full)
    if d.skip_reason == "unknown_extension":
        evolution.queue_unknown_extension(full.suffix or "?")
        if skip_tracker is not None:
            skip_tracker.record_skip(ext_key, "unknown_extension", st.st_size)
        return ("unknown_extension", None)
    if d.skip_reason == "no_grammar":
        evolution.queue_unknown_extension(full.suffix or "?")
        if d.grammar_name:
            _LOG.debug("no grammar package for %s (grammar=%s)", rel, d.grammar_name)
        if skip_tracker is not None:
            skip_tracker.record_skip(
                ext_key, "no_grammar", st.st_size, grammar_name=d.grammar_name
            )
        return ("no_grammar", None)
    if not d.language or not d.inferred_lang:
        if skip_tracker is not None:
            skip_tracker.record_skip(
                ext_key, "no_grammar", st.st_size, grammar_name=d.grammar_name or None
            )
        return ("no_grammar", None)

    try:
        with full.open("rb") as bf:
            probe = bf.read(8192)
    except OSError as e:
        _LOG.warning("read probe %s: %s", rel, e)
        return ("error", None)
    if b"\x00" in probe:
        if skip_tracker is not None:
            skip_tracker.record_skip(ext_key, "binary", st.st_size)
        return ("binary", None)

    try:
        text = full.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        _LOG.warning("read %s: %s", rel, e)
        return ("error", None)

    m0 = load_merged_hints(d.inferred_lang, parse_mode=pm)
    if not text.strip():
        evolution.observe_parse(
            d.grammar_name,
            0.0,
            set(),
            _known_union(m0),
            parse_mode=m0.parse_mode,
        )
        if skip_tracker is not None:
            skip_tracker.add_parsed(text)
        return (None, d.grammar_name)

    lang = d.language
    m = m0
    try:
        ingest_universal_to_store(
            store,
            rel,
            text,
            d.inferred_lang,
            lang,
            parse_mode=pm,
            merged_hints=m,
            is_tsx=d.is_tsx,
        )
    except (OSError, ValueError, RuntimeError) as e:
        _LOG.warning("ingest %s: %s", rel, e)
        return ("error", None)
    try:
        store.commit()
    except (OSError, ValueError) as e:
        _LOG.warning("commit %s: %s", rel, e)
        return ("error", None)

    qgram = _quality_grammar(d.grammar_name, full, d.is_tsx)
    stats = parse_stats_for_universal_ingest(
        store, rel, text, grammar=d.grammar_name, language=lang, is_tsx=d.is_tsx
    )
    q = compute_score_v2(quality_inputs_from_parsed_stats(stats), qgram)
    types = top_level_syntactic_types(lang, text)
    evolution.observe_parse(
        d.grammar_name,
        q,
        types,
        _known_union(m),
        parse_mode=m.parse_mode,
    )
    if skip_tracker is not None:
        skip_tracker.add_parsed(text)
    return (None, d.grammar_name)


def ingest_unified_codebase(
    target_root: str, store: GraphStore, *, parse_mode: str | None = None
) -> IngestTotals:
    """Full-tree ingest + observation for ``omnix analyze``."""
    r = Path(target_root).resolve()
    tot = IngestTotals()
    agg = tot.skip
    for full in iter_dispatch_paths(r, skip_tracker=agg):
        t, gname = ingest_one_path(
            store, r, full, parse_mode=parse_mode, skip_tracker=agg
        )
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
