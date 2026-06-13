"""Per-process Tree-sitter parse cache: identical-bytes elision and incremental reparse (14b-4)."""

from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict
from dataclasses import dataclass

from tree_sitter import Language, Parser, Tree

_MAX_ENTRIES = 1000
_LOG_MILESTONES: frozenset[int] = frozenset(
    (101, 200, 300, 400, 500, 600, 700, 800, 900, 1000)
)

_LOG = logging.getLogger(__name__)
_eviction_total: int = 0
_logged_milestones: set[int] = set()


@dataclass
class _CacheItem:
    source_fp: str
    tree: Tree


# (grammar_id, file_key) -> _CacheItem
_lru: OrderedDict[tuple[str, str], _CacheItem] = OrderedDict()
_gram: dict[str, Parser] = {}


def get_shared_parser(grammar: str, language: Language) -> Parser:
    """One :class:`Parser` per logical grammar in this process (saves init cost)."""
    if grammar not in _gram:
        _gram[grammar] = Parser(language)
    return _gram[grammar]


def _source_fingerprint(b: bytes) -> str:
    return hashlib.blake2b(b, digest_size=16).hexdigest()


def _maybe_log_lru(n: int) -> None:
    global _logged_milestones
    if n not in _LOG_MILESTONES:
        return
    if n in _logged_milestones:
        return
    _logged_milestones.add(n)
    _LOG.info(
        "omnix tree-sitter parse LRU: %d entries (cap %d, evicted_total=%d)",
        n,
        _MAX_ENTRIES,
        _eviction_total,
    )


def _evict_one() -> None:
    global _eviction_total
    if not _lru:
        return
    _lru.popitem(last=False)
    _eviction_total += 1


def parse_tree_cached(grammar_id: str, file_key: str, parser: Parser, source: bytes) -> Tree:
    """
    Return a :class:`Tree` for *source*, using:

    1) LRU hit with same bytes fingerprint: no parse (e.g. pass2 reuses pass1).
    2) Otherwise full parse. Tree-sitter incremental parsing requires explicit
       edit ranges on the old tree; reusing it for arbitrary changed bytes can
       corrupt node byte offsets (notably LF -> CRLF on Windows).
    """
    if not source:
        return parser.parse(source)
    k = (grammar_id, file_key)
    h = _source_fingerprint(source)
    if k in _lru:
        it = _lru[k]
        if it.source_fp == h:
            _lru.move_to_end(k)
            return it.tree
    t = parser.parse(source)
    _lru[k] = _CacheItem(h, t)
    _lru.move_to_end(k)
    while len(_lru) > _MAX_ENTRIES:
        _evict_one()
    _maybe_log_lru(len(_lru))
    return t


def lru_size() -> int:
    return len(_lru)
