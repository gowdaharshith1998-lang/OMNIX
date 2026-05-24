"""Regression test for full Commons Lang 2.6 StringUtils overload emission."""

from __future__ import annotations

from pathlib import Path

import pytest

from omnix.graph.store import GraphStore
from omnix.orchestrator.graph_adapter import populate_from_semantic_nodes
from omnix.semantic.java.parser import JAR_PATH, parse_file

STRINGUTILS_PATH = Path(
    "tests/fixtures/java/commons-lang-2.6/src/main/java/org/apache/commons/lang/StringUtils.java"
)


@pytest.mark.skipif(
    not JAR_PATH.exists(),
    reason="vendored emitter JAR missing - run scripts/vendor_javaparser.sh",
)
def test_java_enricher_persists_all_stringutils_method_and_constructor_nodes(
    tmp_path: Path,
) -> None:
    nodes = parse_file(STRINGUTILS_PATH)
    method_nodes = [n for n in nodes if n.kind == "method"]

    store = GraphStore(str(tmp_path / "omnix.db"))
    try:
        populate_from_semantic_nodes(store, method_nodes)
        persisted_nodes = list(store.iter_all_nodes())
    finally:
        store.close()

    assert len(method_nodes) == 177
    assert len(persisted_nodes) == 177, (
        "Expected every Commons Lang 2.6 StringUtils method+constructor node to "
        "survive graph persistence. A lower count means overload node ids are "
        "colliding and later declarations are replacing earlier ones."
    )
