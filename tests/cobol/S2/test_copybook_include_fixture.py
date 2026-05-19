from __future__ import annotations

from pathlib import Path

from omnix.graph.store import GraphStore
from omnix.parser.cobol.parser import ingest_cobol_to_store


def test_tc201c_emits_copybook_include_edge(tmp_path: Path) -> None:
    root = Path("tests/fixtures/cobol/nist")
    store = GraphStore(str(tmp_path / "graph.db"))
    ingest_cobol_to_store(
        store,
        "tests/fixtures/cobol/nist/TC201C.cob",
        (root / "TC201C.cob").read_text(encoding="utf-8"),
        copybook_paths=[str(root / "copybooks")],
    )

    rows = store.sqlite_connection().execute(
        "SELECT source_id, target_id, relationship, metadata FROM edges WHERE relationship = 'CopybookInclude'"
    ).fetchall()

    assert len(rows) == 1
    assert rows[0]["target_id"].endswith("CUSTREC")
    assert '"resolved": true' in rows[0]["metadata"]
    store.close()
