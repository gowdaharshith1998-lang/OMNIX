"""Tests for universal Tree-sitter parser, grammar detection, hints, quality (ITER 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.graph.store import GraphStore
from src.parser import hint_loader, quality, universal
from src.parser.grammar_detect import (
    detect_for_path,
    try_load_language_for_grammar,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
RUST_DIR = FIXTURES / "rust_sample"


# --- quality.py ---


def test_quality_empty_file() -> None:
    s = quality.compute_score(
        quality.QualityInputs(
            n_functions=0,
            n_classes=0,
            n_imports=0,
            n_call_edges=0,
            n_lines=0,
            function_class_names=(),
        )
    )
    assert s == 0.0


def test_quality_combined_components() -> None:
    s = quality.compute_score(
        quality.QualityInputs(
            n_functions=2,
            n_classes=1,
            n_imports=1,
            n_call_edges=3,
            n_lines=100,
            function_class_names=("foo", "Bar"),
        )
    )
    # 0.3 + 0.2 + 0.2 + 0.2 + 0.2 (ids) = 0.9; density 2/100 < 0.05 so no +0.1
    assert s == 0.9


def test_quality_anonymous_names_reduce_identifier_bonus() -> None:
    s_ok = quality.compute_score(
        quality.QualityInputs(
            n_functions=1,
            n_classes=0,
            n_imports=0,
            n_call_edges=0,
            n_lines=5,
            function_class_names=("real_name",),
        )
    )
    s_bad = quality.compute_score(
        quality.QualityInputs(
            n_functions=1,
            n_classes=0,
            n_imports=0,
            n_call_edges=0,
            n_lines=5,
            function_class_names=("anonymous_1",),
        )
    )
    assert s_ok > s_bad


# --- grammar_detect ---


def test_detect_python_extension() -> None:
    r = detect_for_path(Path("x.py"))
    assert r.inferred_lang == "python"
    assert r.grammar_name == "python"
    assert r.skip_reason is None
    assert r.language is not None


def test_detect_typescript_js_extensions() -> None:
    for name in ("a.ts", "b.tsx", "c.js", "d.jsx"):
        r = detect_for_path(Path(name))
        assert r.grammar_name == "typescript"
        assert r.skip_reason is None
        assert r.language is not None


def test_unknown_extension_recorded() -> None:
    r = detect_for_path(Path("foo.unknownext987"))
    assert r.grammar_name == ""
    assert r.skip_reason == "unknown_extension"


def test_no_grammar_when_module_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.parser import grammar_detect as gd

    def _no_load(_: str) -> object | None:
        return None

    monkeypatch.setattr(gd, "try_load_language_for_grammar", _no_load)
    r2 = detect_for_path(Path("x.zig"))
    assert r2.skip_reason == "no_grammar"


# --- hint_loader ---


def test_hint_merges_extra_function_nodes() -> None:
    m = hint_loader.load_merged_hints("rust", parse_mode="hinted")
    assert "function_signature_item" in m.all_function_node_types
    assert "function_definition" in m.all_function_node_types


def test_load_missing_hint_is_empty_extra_sets() -> None:
    m = hint_loader.load_merged_hints("nonexistent_lang_xyz", parse_mode="generic")
    # generic-only: no file
    assert m.parse_mode == "generic"
    assert not m.hint


# --- universal parse ---


def _tmp_store() -> GraphStore:
    return GraphStore(":memory:")


def test_parse_malformed_source_no_crash() -> None:
    st = _tmp_store()
    r = detect_for_path(Path("x.py"))
    assert r.language is not None
    # garbage should not raise
    universal.ingest_universal_to_store(
        st, "bad.py", "\x00(\x00((( invalid", "python", r.language, parse_mode="generic"
    )
    st.close()


SAMPLE_PY = '''
import os

def foo():
    return 1

class Bar:
    def baz(self):
        return 2

def qux():
    return foo()
'''


def test_generic_python_via_universal_parser_matches_dedicated_output() -> None:
    from src.parser.python_parser import parse_python_files

    import tempfile

    st_u = _tmp_store()
    st_d = _tmp_store()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "mod.py"
        p.write_text(SAMPLE_PY, encoding="utf-8")
        r = detect_for_path(p)
        assert r.language is not None
        rel = "mod.py"
        universal.ingest_universal_to_store(
            st_u, rel, SAMPLE_PY, "python", r.language, parse_mode="generic"
        )
        target = str(Path(td).resolve())
        parse_python_files(target, st_d)
    u_fn = {n.id for n in st_u.get_all_nodes() if n.type in ("function", "method")}
    d_fn = {n.id for n in st_d.get_all_nodes() if n.type in ("function", "method")}
    assert u_fn == d_fn
    u_c = {n.id for n in st_u.get_all_nodes() if n.type == "class"}
    d_c = {n.id for n in st_d.get_all_nodes() if n.type == "class"}
    assert u_c == d_c
    u_e = {(e.source_id, e.target_id, e.relationship) for e in st_u.get_all_edges()}
    d_e = {(e.source_id, e.target_id, e.relationship) for e in st_d.get_all_edges()}
    assert u_e == d_e
    st_u.close()
    st_d.close()


def test_generic_rust_extracts_functions() -> None:
    if try_load_language_for_grammar("rust") is None:
        pytest.skip("tree_sitter_rust not installed")
    rs = RUST_DIR / "sample.rs"
    assert rs.is_file()
    text = rs.read_text(encoding="utf-8")
    st = _tmp_store()
    r = detect_for_path(rs)
    assert r.skip_reason is None
    m = hint_loader.load_merged_hints("rust", parse_mode="hinted")
    universal.ingest_universal_to_store(
        st,
        "sample.rs",
        text,
        "rust",
        r.language,  # type: ignore[arg-type]
        parse_mode=m.parse_mode,
        merged_hints=m,
    )
    ids = {n.name for n in st.get_all_nodes() if n.type in ("function", "method")}
    assert "add" in ids
    assert "main" in ids
    st.close()


def test_hinted_rust_impl_blocks_produce_class_nodes() -> None:
    if try_load_language_for_grammar("rust") is None:
        pytest.skip("tree_sitter_rust not installed")
    rs = RUST_DIR / "sample.rs"
    text = rs.read_text(encoding="utf-8")
    st = _tmp_store()
    r = detect_for_path(rs)
    m = hint_loader.load_merged_hints("rust", parse_mode="hinted")
    universal.ingest_universal_to_store(
        st,
        "sample.rs",
        text,
        "rust",
        r.language,  # type ignore
        parse_mode="hinted",
        merged_hints=m,
    )
    cnames = {n.name for n in st.get_all_nodes() if n.type == "class"}
    assert "Calculator" in cnames
    st.close()


def test_rust_call_edge_main_to_new() -> None:
    if try_load_language_for_grammar("rust") is None:
        pytest.skip("tree_sitter_rust not installed")
    rs = RUST_DIR / "sample.rs"
    text = rs.read_text(encoding="utf-8")
    st = _tmp_store()
    r = detect_for_path(rs)
    m = hint_loader.load_merged_hints("rust", parse_mode="hinted")
    universal.ingest_universal_to_store(
        st,
        "sample.rs",
        text,
        "rust",
        r.language,  # type: ignore
        parse_mode="hinted",
        merged_hints=m,
    )
    calls = st.get_all_edges()
    have = {(e.source_id, e.target_id) for e in calls if e.relationship == "CALLS"}
    main = "sample.rs::main"
    newm = "sample.rs::Calculator::new"
    assert (main, newm) in have
    st.close()
