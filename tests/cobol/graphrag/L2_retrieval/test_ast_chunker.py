from __future__ import annotations

from dataclasses import dataclass, field

from omnix.graph.store import GraphStore


@dataclass
class FakeNode:
    type: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    children: list["FakeNode"] = field(default_factory=list)

    @property
    def start_point(self) -> tuple[int, int]:
        return (self.start_line - 1, 0)

    @property
    def end_point(self) -> tuple[int, int]:
        return (self.end_line - 1, 0)


def test_line_fallback_when_grammar_unavailable(monkeypatch) -> None:
    from omnix.retrieval import ast_chunker

    monkeypatch.setattr(ast_chunker, "_COBOL_LANG", None)
    monkeypatch.setenv("OMNIX_CHUNK_MODE", "auto")

    chunks = ast_chunker.chunk_cobol("IDENTIFICATION DIVISION.\nPROGRAM-ID. HELLO.\n", max_chars=24)

    assert chunks
    assert {chunk.node_kind for chunk in chunks} == {"line_fallback"}


def test_ast_mode_raises_when_grammar_unavailable(monkeypatch) -> None:
    from omnix.retrieval import ast_chunker

    monkeypatch.setattr(ast_chunker, "_COBOL_LANG", None)
    monkeypatch.setenv("OMNIX_CHUNK_MODE", "ast")

    try:
        ast_chunker.chunk_cobol("IDENTIFICATION DIVISION.\n", max_chars=24)
    except RuntimeError as exc:
        assert "tree-sitter COBOL grammar unavailable" in str(exc)
    else:
        raise AssertionError("expected strict AST mode to fail without grammar")


def test_greedy_merge_split_recurses_oversize_ast_nodes() -> None:
    from omnix.retrieval.ast_chunker import _greedy_merge_split

    source = "A" * 8 + "B" * 8 + "C" * 8
    root = FakeNode(
        "root",
        0,
        len(source),
        1,
        3,
        children=[
            FakeNode(
                "large_section",
                0,
                len(source),
                1,
                3,
                children=[
                    FakeNode("paragraph", 0, 8, 1, 1),
                    FakeNode("paragraph", 8, 16, 2, 2),
                    FakeNode("paragraph", 16, 24, 3, 3),
                ],
            )
        ],
    )
    out = []

    _greedy_merge_split(root, source, 10, out)

    assert [chunk.text for chunk in out] == ["A" * 8, "B" * 8, "C" * 8]
    assert all(chunk.node_kind == "paragraph" for chunk in out)


def test_small_ast_siblings_merge_under_limit() -> None:
    from omnix.retrieval.ast_chunker import _greedy_merge_split

    source = "01 A.\n01 B.\n01 C.\n"
    root = FakeNode(
        "data_division",
        0,
        len(source),
        1,
        3,
        children=[
            FakeNode("data_item", 0, 6, 1, 1),
            FakeNode("data_item", 6, 12, 2, 2),
            FakeNode("data_item", 12, 18, 3, 3),
        ],
    )
    out = []

    _greedy_merge_split(root, source, 32, out)

    assert len(out) == 1
    assert out[0].text == source
    assert out[0].node_kind == "data_item"


def test_vector_index_uses_explicit_chunk_mode_and_returns_base_node(tmp_path, monkeypatch) -> None:
    from omnix.retrieval.vector_index import VectorIndex

    monkeypatch.setenv("OMNIX_CHUNK_MODE", "line")
    store = GraphStore(str(tmp_path / "graph.db"))
    source = "\n".join(f"DISPLAY 'LINE {idx}'." for idx in range(12))
    store.add_node(
        "prog:BIG",
        "BIG",
        "CobolProgram",
        file_path=str(tmp_path / "BIG.cob"),
        metadata={"source_text": source, "signature_summary": "BIG signature"},
    )
    store.commit()
    try:
        idx = VectorIndex(store)
        idx.rebuild_from_graph(store)
        rows = store.sqlite_connection().execute("SELECT node_id FROM vec_programs").fetchall()
        node_ids = [str(row["node_id"]) for row in rows]

        assert any(node_id.startswith("prog:BIG::chunk:") for node_id in node_ids)
        assert idx.query("LINE 11", "programs", top_k=1)[0][0] == "prog:BIG"
    finally:
        store.close()


def test_vector_index_preserves_default_node_level_indexing(tmp_path, monkeypatch) -> None:
    from omnix.retrieval.vector_index import VectorIndex

    monkeypatch.delenv("OMNIX_CHUNK_MODE", raising=False)
    store = GraphStore(str(tmp_path / "graph.db"))
    store.add_node(
        "prog:HELLO",
        "HELLO",
        "CobolProgram",
        metadata={"source_text": "PROGRAM-ID. HELLO.", "signature_summary": "HELLO signature"},
    )
    store.commit()
    try:
        idx = VectorIndex(store)
        idx.rebuild_from_graph(store)
        rows = store.sqlite_connection().execute("SELECT node_id FROM vec_programs").fetchall()

        assert [str(row["node_id"]) for row in rows] == ["prog:HELLO"]
    finally:
        store.close()
