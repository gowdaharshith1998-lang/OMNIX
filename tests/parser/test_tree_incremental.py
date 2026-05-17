"""14b-4: Tree-sitter parse LRU and incremental reparse (HALT numbers are informative)."""

from __future__ import annotations

import time

import tree_sitter_python as tsp
from tree_sitter import Language

from omnix.parser import tree_parse_cache as tpc


def _fifty_kb_python() -> str:
    line = "def f_{i}() -> None:\n    return {i}\n"
    out: list[str] = []
    n = 0
    while len("".join(out)) < 50_000:
        out.append(line.format(i=n))
        n += 1
    s = "".join(out)
    assert len(s) >= 50_000, len(s)
    return s


def test_parse_cache_same_bytes_returns_same_tree() -> None:
    tpc._lru.clear()  # noqa: SLF001
    tpc._gram.clear()  # noqa: SLF001
    py = Language(tsp.language())
    p = tpc.get_shared_parser("python", py)
    text = "def a():\n  pass\n"
    b = text.encode("utf-8")
    t1 = tpc.parse_tree_cached("python", "x.py", p, b)
    t2 = tpc.parse_tree_cached("python", "x.py", p, b)
    assert t1 is t2


def test_full_vs_incremental_50kb_python() -> None:
    """HALT 14b-4: min wall time over runs (50kB+ source, 1-line edit for incremental)."""
    tpc._lru.clear()  # noqa: SLF001
    tpc._gram.clear()  # noqa: SLF001
    text = _fifty_kb_python()
    b0 = text.encode("utf-8")
    # One-line append (typical small edit; mid-file edits stress more work).
    b1 = b0 + b"\n# omnix_14b4_tail\n"
    p = tpc.get_shared_parser("python", Language(tsp.language()))
    n = 20
    full_times: list[float] = []
    for i in range(n):
        tpc._lru.clear()  # noqa: SLF001
        t0 = time.perf_counter()
        tpc.parse_tree_cached("python", f"full_{i}.py", p, b0)
        full_times.append(time.perf_counter() - t0)
    t_full = min(full_times)

    inc_times: list[float] = []
    for i in range(n):
        tpc._lru.clear()  # noqa: SLF001
        tpc.parse_tree_cached("python", f"inc_{i}.py", p, b0)
        t0 = time.perf_counter()
        tpc.parse_tree_cached("python", f"inc_{i}.py", p, b1)
        inc_times.append(time.perf_counter() - t0)
    t_inc = min(inc_times)

    assert t_full > 0 and t_inc > 0
    print(
        f"\nHALT_14b4 (min of {n}, ~{len(b0) // 1024}kiB) "
        f"full={t_full*1000:.2f}ms incremental={t_inc*1000:.2f}ms speedup={t_full/t_inc:.2f}x\n"
    )
