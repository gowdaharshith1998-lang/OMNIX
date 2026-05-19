"""End-to-end test for omnix.rebuild.runner.

Stub graph + stub dispatch + tmp project — exercises the full pipeline:
analyze → spec gen → LLM dispatch → gates 1-4 → signed receipt emission.
No real LLM call. No real GraphStore. Confirms file layout, honesty gate
(receipts mark not-yet-wired gates 5+6 as skipped), and offline verifiability.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnix.rebuild.runner import RebuildOutput, _run_with_graph
from omnix.receipts.finding_keys import (
    ensure_project_key,
    project_pubkey_path,
)
from omnix.receipts.rebuild_receipt import RebuildReceipt, gates_summary, verify_rebuild
from omnix.semantic import DependencyEdge, SemanticNode, SourceLocation


class _StubGraph:
    def __init__(self, nodes: list[SemanticNode], edges: list[tuple[str, str]]) -> None:
        self._nodes = nodes
        self._edges = edges
        self._by_fqn = {n.fqn: n for n in nodes}

    def get_all_nodes(self):
        return list(self._nodes)

    def get_dependency_edges(self):
        return list(self._edges)

    def get_node(self, fqn: str) -> SemanticNode:
        return self._by_fqn[fqn]

    def get_legacy_signature(self, fqn: str) -> str:
        return ""

    def get_rebuilt_signature(self, fqn: str) -> str | None:
        return None


def _make_node(fqn: str, source_file: str) -> SemanticNode:
    return SemanticNode(
        fqn=fqn,
        kind="method",
        signature=f"public static String {fqn.rsplit('.', 1)[-1]}(String)",
        resolved_param_types=("java.lang.String",),
        resolved_return_type="java.lang.String",
        dependency_edges=(),
        source_location=SourceLocation(file_path=source_file, line=1, column=0),
    )


def _write(p: Path, body: str) -> str:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p.name


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, _StubGraph, Path]:
    """Set up tmp project with one Java source + a fresh project keypair."""
    monkeypatch.setenv("HOME", str(tmp_path))
    project_root = tmp_path / "proj"
    project_root.mkdir()
    src_rel = _write(
        project_root / "src" / "Foo.java",
        "public class Foo { public static String bar(String s) { return s; } }",
    )
    nodes = [_make_node("com.x.Foo.bar", f"src/{src_rel}")]
    graph = _StubGraph(nodes, [])

    ensure_project_key(project_root)
    pub_path = project_pubkey_path(project_root)
    return project_root, graph, pub_path


def _good_rebuild_source() -> str:
    """A rebuild that should pass gates 1-3."""
    return (
        "public class Foo {\n"
        "    public static String bar(String s) {\n"
        "        return s;\n"
        "    }\n"
        "}\n"
    )


def test_runner_emits_one_receipt_per_node(project) -> None:
    project_root, graph, _ = project

    outputs = _run_with_graph(
        graph=graph,
        project_path=project_root,
        target_language="java21",
        node_filter=None,
        dispatch_fn=lambda prompt, model="claude-opus-4.7": _good_rebuild_source(),
        model="claude-opus-4.7",
        output_root=None,
    )
    assert len(outputs) == 1
    o: RebuildOutput = outputs[0]
    assert o.node_fqn == "com.x.Foo.bar"
    assert o.receipt_path.exists()
    assert o.signature_path.exists()
    assert o.rebuilt_source_path.exists()
    assert o.receipt_path.parent == o.signature_path.parent == o.rebuilt_source_path.parent


def test_receipt_contains_all_six_gates_with_real_gate5_and_gate6_skipped(
    project,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root, graph, _ = project

    from omnix.gates import gate5_property

    def _passing_gate5(legacy_source: str, rebuilt_source: str, semantic_node: SemanticNode):
        assert legacy_source == (project_root / "src" / "Foo.java").read_text(encoding="utf-8")
        assert rebuilt_source == _good_rebuild_source()
        assert semantic_node.fqn == "com.x.Foo.bar"
        return gate5_property.Gate5Evaluation(
            status="passed",
            details={"status": "passed", "examples_used": 200},
        )

    monkeypatch.setattr(gate5_property, "evaluate", _passing_gate5)

    outputs = _run_with_graph(
        graph=graph,
        project_path=project_root,
        target_language="java21",
        node_filter=None,
        dispatch_fn=lambda prompt, model="claude-opus-4.7": _good_rebuild_source(),
        model="claude-opus-4.7",
        output_root=None,
    )
    receipt_dict = json.loads(outputs[0].receipt_path.read_text(encoding="utf-8"))
    receipt = RebuildReceipt.from_dict(receipt_dict)

    gate_status_by_number = {g.gate_number: g.status for g in receipt.gate_results}
    assert sorted(gate_status_by_number) == [1, 2, 3, 4, 5, 6]
    assert gate_status_by_number[5] == "passed"
    assert gate_status_by_number[6] == "skipped"
    # Gate 4 not yet wired mechanically — emitted as 'skipped'.
    assert gate_status_by_number[4] == "skipped"


def test_receipt_records_gate5_inconclusive_in_summary(
    project,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnix.gates import gate5_property
    from omnix.gates.result import GateError

    project_root, graph, _ = project

    def _inconclusive_gate5(
        legacy_source: str,
        rebuilt_source: str,
        semantic_node: SemanticNode,
    ) -> gate5_property.Gate5Evaluation:
        err = GateError(
            gate_number=5,
            gate_name="property_based",
            message="under-tested",
            details={
                "status": "inconclusive",
                "reason": "high_assume_rejection_rate",
                "examples_tried": 200,
                "examples_used": 50,
            },
        )
        return gate5_property.Gate5Evaluation(
            status="inconclusive",
            details=dict(err.details),
            error=err,
        )

    monkeypatch.setattr(gate5_property, "evaluate", _inconclusive_gate5)

    outputs = _run_with_graph(
        graph=graph,
        project_path=project_root,
        target_language="java21",
        node_filter=None,
        dispatch_fn=lambda prompt, model="claude-opus-4.7": _good_rebuild_source(),
        model="claude-opus-4.7",
        output_root=None,
    )
    receipt = RebuildReceipt.from_dict(
        json.loads(outputs[0].receipt_path.read_text(encoding="utf-8"))
    )
    gate5 = next(g for g in receipt.gate_results if g.gate_number == 5)
    assert gate5.status == "inconclusive"
    assert gate5.details["examples_used"] == 50
    assert gates_summary(receipt.gate_results) == (
        "3-passed/0-failed/2-skipped/1-inconclusive/0-deferred_m3"
    )


def test_skip_gate5_keeps_receipt_verifiable_with_user_skip_reason(project) -> None:
    project_root, graph, pub_path = project
    outputs = _run_with_graph(
        graph=graph,
        project_path=project_root,
        target_language="java21",
        node_filter=None,
        dispatch_fn=lambda prompt, model="claude-opus-4.7": _good_rebuild_source(),
        model="claude-opus-4.7",
        output_root=None,
        skip_gate_5=True,
    )
    receipt = RebuildReceipt.from_dict(
        json.loads(outputs[0].receipt_path.read_text(encoding="utf-8"))
    )
    gate5 = next(g for g in receipt.gate_results if g.gate_number == 5)
    assert gate5.status == "skipped"
    assert gate5.details["reason"] == "skipped_by_user"
    sig_b64 = outputs[0].signature_path.read_text(encoding="utf-8").strip()
    assert verify_rebuild(receipt, sig_b64, pub_path) is True


def test_receipt_verifies_offline(project) -> None:
    project_root, graph, pub_path = project
    outputs = _run_with_graph(
        graph=graph,
        project_path=project_root,
        target_language="java21",
        node_filter=None,
        dispatch_fn=lambda prompt, model="claude-opus-4.7": _good_rebuild_source(),
        model="claude-opus-4.7",
        output_root=None,
    )
    receipt_dict = json.loads(outputs[0].receipt_path.read_text(encoding="utf-8"))
    receipt = RebuildReceipt.from_dict(receipt_dict)
    sig_b64 = outputs[0].signature_path.read_text(encoding="utf-8").strip()
    assert verify_rebuild(receipt, sig_b64, pub_path) is True


def test_tampered_receipt_fails_verification(project) -> None:
    project_root, graph, pub_path = project
    outputs = _run_with_graph(
        graph=graph,
        project_path=project_root,
        target_language="java21",
        node_filter=None,
        dispatch_fn=lambda prompt, model="claude-opus-4.7": _good_rebuild_source(),
        model="claude-opus-4.7",
        output_root=None,
    )
    receipt_path = outputs[0].receipt_path
    receipt_dict = json.loads(receipt_path.read_text(encoding="utf-8"))
    # Flip the rebuilt-source hash — tamper at the most semantically important field.
    receipt_dict["rebuilt_source_sha256"] = "0" * 64
    tampered = RebuildReceipt.from_dict(receipt_dict)
    sig_b64 = outputs[0].signature_path.read_text(encoding="utf-8").strip()
    assert verify_rebuild(tampered, sig_b64, pub_path) is False


def test_receipt_records_legacy_source_hash(project) -> None:
    """The receipt anchors the *exact* legacy source bytes — so a future
    repo reader can reconstruct what was rebuilt."""
    import hashlib

    project_root, graph, _ = project
    outputs = _run_with_graph(
        graph=graph,
        project_path=project_root,
        target_language="java21",
        node_filter=None,
        dispatch_fn=lambda prompt, model="claude-opus-4.7": _good_rebuild_source(),
        model="claude-opus-4.7",
        output_root=None,
    )
    receipt_dict = json.loads(outputs[0].receipt_path.read_text(encoding="utf-8"))
    expected = hashlib.sha256(
        (project_root / "src" / "Foo.java").read_bytes()
    ).hexdigest()
    assert receipt_dict["legacy_source_sha256"] == expected


def test_node_filter_restricts_to_matching_fqn(project, tmp_path: Path) -> None:
    """fnmatch pattern on node FQN — used by `--node-filter` CLI flag."""
    project_root, _graph, _ = project
    # Augment with a second node we don't want to match.
    _write(
        project_root / "src" / "Other.java",
        "public class Other { public static String other(String s) { return s; } }",
    )
    nodes = [
        _make_node("com.x.Foo.bar", "src/Foo.java"),
        _make_node("com.x.Other.other", "src/Other.java"),
    ]
    graph = _StubGraph(nodes, [])

    outputs = _run_with_graph(
        graph=graph,
        project_path=project_root,
        target_language="java21",
        node_filter="*Foo.bar",
        dispatch_fn=lambda prompt, model="claude-opus-4.7": _good_rebuild_source(),
        model="claude-opus-4.7",
        output_root=None,
    )
    assert [o.node_fqn for o in outputs] == ["com.x.Foo.bar"]


def test_node_filter_empty_match_raises(project) -> None:
    from omnix.orchestrator.dispatcher import OrchestratorError

    project_root, graph, _ = project
    with pytest.raises(OrchestratorError, match="matched zero nodes"):
        _run_with_graph(
            graph=graph,
            project_path=project_root,
            target_language="java21",
            node_filter="does.not.match.anything",
            dispatch_fn=lambda prompt, model="claude-opus-4.7": _good_rebuild_source(),
            model="claude-opus-4.7",
            output_root=None,
        )
