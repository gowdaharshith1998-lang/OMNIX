"""Tests for omnix.orchestrator.dispatcher.

Use a hand-rolled stub graph (the real GraphStore is intentionally untouched
in unit tests — that integration is the xfail tripwire at the bottom of the
file).

Each stub call records the prompt + model so we can assert dispatch order,
hash shape, model propagation, and SCC fan-out behavior.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from omnix.orchestrator.attempt import RebuildAttempt
from omnix.orchestrator.dispatcher import _run_with_graph
from omnix.semantic import DependencyEdge, SemanticNode, SourceLocation

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class _StubGraph:
    """Minimal graph implementing the slice the orchestrator uses.

    Holds:
      - a list of SemanticNodes,
      - a list of (src_fqn, dst_fqn) dependency edges,
      - an optional legacy-signature map for the dependencies pass.
    """

    def __init__(
        self,
        nodes: list[SemanticNode],
        edges: list[tuple[str, str]],
        legacy_signatures: dict[str, str] | None = None,
    ) -> None:
        self._nodes = nodes
        self._edges = edges
        self._by_fqn = {n.fqn: n for n in nodes}
        self._legacy = legacy_signatures or {}

    def get_all_nodes(self):
        return list(self._nodes)

    def get_dependency_edges(self):
        return list(self._edges)

    def get_node(self, fqn: str) -> SemanticNode:
        return self._by_fqn[fqn]

    # Consumed by spec.passes.dependencies via duck-typing.
    def get_legacy_signature(self, fqn: str) -> str:
        return self._legacy.get(fqn, "")

    def get_rebuilt_signature(self, fqn: str) -> str | None:
        return None


def _make_node(
    fqn: str,
    source_file: str,
    deps: list[str] | None = None,
) -> SemanticNode:
    return SemanticNode(
        fqn=fqn,
        kind="method",
        signature=f"public static String {fqn.rsplit('.', 1)[-1]}(String)",
        resolved_param_types=("java.lang.String",),
        resolved_return_type="java.lang.String",
        dependency_edges=tuple(
            DependencyEdge(target_fqn=d, kind="calls", line=1) for d in (deps or [])
        ),
        source_location=SourceLocation(file_path=source_file, line=1, column=0),
    )


def _write_source(tmp_path: Path, rel_path: str, body: str = "// stub") -> str:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(body, encoding="utf-8")
    return rel_path


def _linear_chain_graph(tmp_path: Path) -> _StubGraph:
    # A depends on B depends on C — dispatch order: C, B, A.
    rel_a = _write_source(tmp_path, "src/A.java", "class A{}")
    rel_b = _write_source(tmp_path, "src/B.java", "class B{}")
    rel_c = _write_source(tmp_path, "src/C.java", "class C{}")
    nodes = [
        _make_node("com.x.A", rel_a, deps=["com.x.B"]),
        _make_node("com.x.B", rel_b, deps=["com.x.C"]),
        _make_node("com.x.C", rel_c, deps=[]),
    ]
    edges = [("com.x.A", "com.x.B"), ("com.x.B", "com.x.C")]
    return _StubGraph(nodes, edges)


def test_run_calls_dispatch_once_per_node(tmp_path: Path) -> None:
    graph = _linear_chain_graph(tmp_path)
    seen: list[str] = []

    def stub(prompt_text: str, *, model: str) -> str:
        # Pull FQN out of the spec JSON section.
        seen.append(prompt_text)
        return "// rebuilt"

    attempts = _run_with_graph(
        graph=graph,
        project_path=tmp_path,
        target_language="java21",
        dispatch_fn=stub,
        model="test-model",
    )
    assert len(attempts) == 3
    assert len(seen) == 3
    assert all(isinstance(a, RebuildAttempt) for a in attempts)


def test_run_respects_topo_order(tmp_path: Path) -> None:
    graph = _linear_chain_graph(tmp_path)
    call_order: list[str] = []

    def stub(prompt_text: str, *, model: str) -> str:
        # Extract fqn from the spec JSON in the prompt.
        match = re.search(r'"fqn":\s*"([^"]+)"', prompt_text)
        assert match, f"prompt missing fqn: {prompt_text[:200]}"
        call_order.append(match.group(1))
        return f"// rebuilt: {match.group(1)}"

    _run_with_graph(
        graph=graph,
        project_path=tmp_path,
        target_language="java21",
        dispatch_fn=stub,
        model="test-model",
    )
    # C has no deps, so it's dispatched first; A depends on B depends on C, so A is last.
    assert call_order == ["com.x.C", "com.x.B", "com.x.A"]


def test_run_records_spec_hash_and_prompt_hash(tmp_path: Path) -> None:
    graph = _linear_chain_graph(tmp_path)

    def stub(prompt_text: str, *, model: str) -> str:
        return "// rebuilt"

    attempts = _run_with_graph(
        graph=graph,
        project_path=tmp_path,
        target_language="java21",
        dispatch_fn=stub,
        model="test-model",
    )
    for a in attempts:
        assert _SHA256_RE.match(a.spec_hash), f"bad spec_hash: {a.spec_hash}"
        assert _SHA256_RE.match(a.prompt_text_hash), f"bad prompt hash: {a.prompt_text_hash}"


def test_run_propagates_dispatch_error(tmp_path: Path) -> None:
    graph = _linear_chain_graph(tmp_path)

    class BoomError(RuntimeError):
        pass

    def stub(prompt_text: str, *, model: str) -> str:
        raise BoomError("fabric blew up")

    with pytest.raises(BoomError, match="fabric blew up"):
        _run_with_graph(
            graph=graph,
            project_path=tmp_path,
            target_language="java21",
            dispatch_fn=stub,
            model="test-model",
        )


def test_run_with_scc_produces_one_attempt_per_scc_member_with_shared_response(
    tmp_path: Path,
) -> None:
    # A <-> B mutual recursion + standalone C dependency-free.
    rel_a = _write_source(tmp_path, "src/A.java", "class A { void a(){ b(); } }")
    rel_b = _write_source(tmp_path, "src/B.java", "class B { void b(){ a(); } }")
    rel_c = _write_source(tmp_path, "src/C.java", "class C {}")
    nodes = [
        _make_node("com.x.A", rel_a, deps=["com.x.B"]),
        _make_node("com.x.B", rel_b, deps=["com.x.A"]),
        _make_node("com.x.C", rel_c, deps=[]),
    ]
    edges = [
        ("com.x.A", "com.x.B"),
        ("com.x.B", "com.x.A"),
    ]
    graph = _StubGraph(nodes, edges)

    counter = {"n": 0}

    def stub(prompt_text: str, *, model: str) -> str:
        counter["n"] += 1
        return f"// batch response {counter['n']}"

    attempts = _run_with_graph(
        graph=graph,
        project_path=tmp_path,
        target_language="java21",
        dispatch_fn=stub,
        model="test-model",
    )
    # 3 attempts total (A, B from SCC; C standalone).
    assert len(attempts) == 3
    # SCC produced 2 attempts sharing response_text + prompt_text_hash.
    by_fqn = {a.node_fqn: a for a in attempts}
    assert by_fqn["com.x.A"].response_text == by_fqn["com.x.B"].response_text
    assert by_fqn["com.x.A"].prompt_text_hash == by_fqn["com.x.B"].prompt_text_hash
    # C is independent → distinct prompt hash.
    assert by_fqn["com.x.C"].prompt_text_hash != by_fqn["com.x.A"].prompt_text_hash
    # Only 2 LLM calls (one for SCC, one for C), not 3.
    assert counter["n"] == 2


def test_run_records_model_identifier(tmp_path: Path) -> None:
    graph = _linear_chain_graph(tmp_path)

    def stub(prompt_text: str, *, model: str) -> str:
        return "// rebuilt"

    attempts = _run_with_graph(
        graph=graph,
        project_path=tmp_path,
        target_language="java21",
        dispatch_fn=stub,
        model="test-model-v9",
    )
    assert {a.model for a in attempts} == {"test-model-v9"}


def test_run_accepts_stub_dispatch_fn_without_model_kwarg(tmp_path: Path) -> None:
    # Some legacy stubs don't accept model=; orchestrator must fall back to
    # positional invocation.
    graph = _linear_chain_graph(tmp_path)

    def stub(prompt_text: str) -> str:
        return "// rebuilt"

    attempts = _run_with_graph(
        graph=graph,
        project_path=tmp_path,
        target_language="java21",
        dispatch_fn=stub,
        model="test-model",
    )
    assert len(attempts) == 3


def test_run_raises_on_missing_source_file(tmp_path: Path) -> None:
    from omnix.orchestrator.dispatcher import OrchestratorError

    nodes = [_make_node("com.x.A", "src/missing.java", deps=[])]
    graph = _StubGraph(nodes, [])

    def stub(prompt_text: str, *, model: str) -> str:
        return "// rebuilt"

    with pytest.raises(OrchestratorError, match="source file missing"):
        _run_with_graph(
            graph=graph,
            project_path=tmp_path,
            target_language="java21",
            dispatch_fn=stub,
            model="m",
        )


@pytest.mark.xfail(
    strict=True,
    reason="real GraphStore + .omnix/omnix.db not provisioned in this test run",
)
def test_e2e_with_real_graph_store(tmp_path: Path) -> None:
    """Tripwire — flips XPASS once the M1 graph-analyze pipeline lands and
    the orchestrator can be driven from a real .omnix/omnix.db.
    """
    from omnix.orchestrator.dispatcher import run

    attempts = run(tmp_path, target_language="java21", dispatch_fn=lambda p: "// stub")
    assert attempts  # placeholder — will be filled in when phase 6 wires it.
