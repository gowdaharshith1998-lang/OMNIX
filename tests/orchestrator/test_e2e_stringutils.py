"""End-to-end orchestrator on the StringUtils.java fixture.

Wires JavaParser-backed parse_file → GraphStore → dispatcher with a stub LLM.
Validates the same dispatch loop production uses, with deterministic responses
instead of real model calls.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from omnix.graph.store import GraphStore
from omnix.orchestrator.dispatcher import run
from omnix.orchestrator.graph_adapter import populate_from_semantic_nodes
from omnix.semantic.java.parser import parse_file

FIXTURE = Path(__file__).parents[1] / "semantic" / "java" / "fixtures" / "StringUtils.java"


def _provision_project(tmp_path: Path) -> Path:
    """Copy StringUtils.java into tmp_path/src/, parse it, populate a real
    GraphStore at tmp_path/.omnix/omnix.db, return tmp_path."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    fixture_copy = src_dir / "StringUtils.java"
    shutil.copy(FIXTURE, fixture_copy)

    nodes = parse_file(fixture_copy)
    assert nodes, "expected parse_file to emit at least one SemanticNode"

    omnix_dir = tmp_path / ".omnix"
    omnix_dir.mkdir()
    store = GraphStore(str(omnix_dir / "omnix.db"))
    populate_from_semantic_nodes(store, nodes)
    store.close()
    return tmp_path


def test_orchestrator_walks_stringutils_methods_in_topo_order(tmp_path: Path) -> None:
    """End-to-end: parse → populate GraphStore → dispatcher.run with stub LLM.

    Asserts:
      - one RebuildAttempt per method emitted by parse_file (reverse, isEmpty,
        isBlank, plus the private constructor)
      - every attempt's node_fqn ends in one of those names
      - SCC-batching is trivial here (no cycles); each attempt is its own SCC
    """
    project = _provision_project(tmp_path)

    attempts = run(project, target_language="java21", dispatch_fn=lambda p: "// rebuilt")

    suffixes = {a.node_fqn.rsplit(".", 1)[-1] for a in attempts}
    assert suffixes >= {"reverse", "isEmpty", "isBlank"}, suffixes
    for a in attempts:
        assert a.response_text == "// rebuilt"
        assert a.model == "claude-opus-4.7"
        assert a.attempt_number == 1
