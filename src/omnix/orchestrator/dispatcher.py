"""Orchestrator dispatcher — walk the graph, dispatch one LLM call per node.

Phase 5 deliverable: pure dispatch loop, no retry (Phase 7), no verification
gates (Phase 6). Each node becomes one RebuildAttempt; each SCC becomes one
LLM call whose response is fanned out to N RebuildAttempts (one per member),
all sharing the same response_text + prompt_text_hash.

The `dispatch_fn` boundary is the seam: tests inject a stub. Production
defaults to `omnix.fabric.dispatcher.dispatch` via a thin adapter that
constructs the payload from prompt text alone.

Errors from `dispatch_fn` propagate up unmodified. Phase 7's retry wrapper
will catch and reissue; this module stays simple.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from omnix.orchestrator.attempt import RebuildAttempt, sha256_hex
from omnix.orchestrator.prompt_template import (
    PROMPT_TEMPLATE_VERSION,
    format_prompt,
    format_scc_prompt,
)
from omnix.orchestrator.topological import topo_sort
from omnix.semantic import SemanticNode
from omnix.spec import Spec
from omnix.spec.generator import generate as _generate_spec

# Re-exported so callers can do `from omnix.orchestrator.dispatcher import run, GraphStoreAdapter`.
# Local import in _load_graph keeps the cold path lazy; this top-level export
# documents the public surface.
__all__ = ["OrchestratorError", "run"]


class OrchestratorError(Exception):
    """Raised by the orchestrator for setup / loading failures.

    Dispatch-time errors from the LLM call itself are not wrapped — they
    propagate as-is so the eventual retry wrapper can introspect them.
    """


class _GraphLike(Protocol):
    """The slice of GraphStore the orchestrator actually uses.

    Documentation-only; not enforced at runtime — tests pass in arbitrary
    stub objects with these methods.
    """

    def get_all_nodes(self) -> Iterable[SemanticNode]: ...
    def get_dependency_edges(self) -> Iterable[tuple[str, str]]: ...
    def get_node(self, fqn: str) -> SemanticNode: ...


# Default LLM dispatch — lazy import so tests never trigger fabric setup.
def _default_dispatch_fn(prompt_text: str, *, model: str) -> str:
    """Production dispatch_fn: forwards to omnix.fabric.dispatcher.dispatch.

    Kept thin on purpose. The orchestrator only cares about a (text in, text
    out) function; fabric handles all routing, budget, dedup, telemetry.
    """
    from omnix.fabric.dispatcher import dispatch  # local import — heavy

    payload: dict[str, Any] = {
        "agent_id": "omnix-orchestrator",
        "task_kind": "rebuild",
        "messages": [{"role": "user", "content": prompt_text}],
        "options": {"model": model},
    }
    result = dispatch(payload)
    # Fabric returns a dict — pull the assistant text out.
    if isinstance(result, dict):
        text = result.get("text") or result.get("content")
        if isinstance(text, str):
            return text
    raise OrchestratorError(f"dispatch_fn returned non-text result: {type(result).__name__}")


def _load_graph(project_path: Path) -> _GraphLike:
    """Open the GraphStore for `project_path` and return a `_GraphLike` adapter.

    The real `GraphStore` exposes `NodeRow` / `EdgeRow`; this seam wraps it in
    `GraphStoreAdapter` so the dispatcher's protocol contract is satisfied.

    Raises OrchestratorError if the module or DB is missing.
    """
    db_path = project_path / ".omnix" / "omnix.db"
    if not db_path.exists():
        raise OrchestratorError(
            f"graph not found at {db_path} — run `omnix analyze` first"
        )
    try:
        from omnix.graph.store import GraphStore  # noqa: WPS433 — runtime import is intentional
        from omnix.orchestrator.graph_adapter import GraphStoreAdapter  # noqa: WPS433
    except ImportError as e:  # pragma: no cover — defensive
        raise OrchestratorError(
            "omnix.graph.store unavailable — run `omnix analyze` first"
        ) from e
    return GraphStoreAdapter(GraphStore(str(db_path)))


def _load_source(node: SemanticNode, project_path: Path) -> str:
    """Read the source text for `node` from disk.

    Resolves `node.source_location.file_path` against `project_path` if it
    is relative. Missing file is fatal — we'd rather fail loud than dispatch
    against an empty source block.
    """
    raw_path = Path(node.source_location.file_path)
    full_path = raw_path if raw_path.is_absolute() else (project_path / raw_path)
    if not full_path.exists():
        raise OrchestratorError(
            f"source file missing for {node.fqn}: {full_path}"
        )
    try:
        return full_path.read_text(encoding="utf-8")
    except OSError as e:
        raise OrchestratorError(
            f"could not read source for {node.fqn} ({full_path}): {e}"
        ) from e


def _collect_graph_inputs(
    graph: _GraphLike,
) -> tuple[list[SemanticNode], list[tuple[str, str]], dict[str, SemanticNode]]:
    """Snapshot the graph into in-memory structures the loop walks.

    Returns (nodes, edges, fqn_index).
    """
    nodes: list[SemanticNode] = list(graph.get_all_nodes())
    fqn_index: dict[str, SemanticNode] = {n.fqn: n for n in nodes}
    edges: list[tuple[str, str]] = []
    for src_fqn, dst_fqn in graph.get_dependency_edges():
        if dst_fqn not in fqn_index:
            # Out-of-graph dependency (e.g. java.lang.String) — drop silently.
            # The spec still records it via dependency edges; topo sort just
            # can't order something it doesn't know about.
            continue
        edges.append((src_fqn, dst_fqn))
    return nodes, edges, fqn_index


def _build_attempt(
    node_fqn: str,
    spec: Spec,
    prompt_text_hash: str,
    response_text: str,
    model: str,
) -> RebuildAttempt:
    """Stamp a RebuildAttempt with consistent hashes + timestamp."""
    return RebuildAttempt(
        node_fqn=node_fqn,
        spec_hash=sha256_hex(spec.to_json()),
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        prompt_text_hash=prompt_text_hash,
        response_text=response_text,
        timestamp=RebuildAttempt.now_utc(),
        model=model,
    )


def run(
    project_path: Path,
    target_language: str = "java21",
    *,
    dispatch_fn: Callable[..., str] | None = None,
    model: str = "claude-opus-4.7",
) -> list[RebuildAttempt]:
    """Walk the graph and dispatch one LLM call per node (or per SCC).

    Args:
        project_path: project root containing `.omnix/omnix.db`.
        target_language: spec target — M1 supports only "java21".
        dispatch_fn: text-in / text-out LLM seam. Defaults to fabric.
            Test stubs typically accept `(prompt_text, *, model=...)` but the
            orchestrator falls back to a positional call for compatibility
            with stubs that don't accept the `model` kwarg.
        model: model identifier recorded on every RebuildAttempt.

    Returns:
        list[RebuildAttempt] in dispatch order. SCCs produce one attempt per
        member with shared response_text + prompt_text_hash.
    """
    graph = _load_graph(project_path)
    return _run_with_graph(
        graph=graph,
        project_path=project_path,
        target_language=target_language,
        dispatch_fn=dispatch_fn,
        model=model,
    )


def _run_with_graph(
    *,
    graph: _GraphLike,
    project_path: Path,
    target_language: str,
    dispatch_fn: Callable[..., str] | None,
    model: str,
) -> list[RebuildAttempt]:
    """Inner loop — split out so tests can inject a fully-stubbed graph
    without round-tripping through `_load_graph`.
    """
    effective_dispatch = dispatch_fn if dispatch_fn is not None else _default_dispatch_fn

    nodes, edges, fqn_index = _collect_graph_inputs(graph)
    order = topo_sort([n.fqn for n in nodes], edges)

    attempts: list[RebuildAttempt] = []
    for entry in order:
        if isinstance(entry, list):
            # SCC: build one batched prompt, fan response into N attempts.
            scc_nodes = [fqn_index[f] for f in entry]
            specs = [_generate_spec(n, graph, target_language) for n in scc_nodes]
            sources = {n.fqn: _load_source(n, project_path) for n in scc_nodes}
            prompt_text, prompt_hash = format_scc_prompt(specs, sources)
            response_text = _invoke(effective_dispatch, prompt_text, model)
            for n, spec in zip(scc_nodes, specs):
                attempts.append(
                    _build_attempt(
                        node_fqn=n.fqn,
                        spec=spec,
                        prompt_text_hash=prompt_hash,
                        response_text=response_text,
                        model=model,
                    )
                )
        else:
            node = fqn_index[entry]
            spec = _generate_spec(node, graph, target_language)
            source = _load_source(node, project_path)
            prompt_text, prompt_hash = format_prompt(spec, source)
            response_text = _invoke(effective_dispatch, prompt_text, model)
            attempts.append(
                _build_attempt(
                    node_fqn=node.fqn,
                    spec=spec,
                    prompt_text_hash=prompt_hash,
                    response_text=response_text,
                    model=model,
                )
            )
    return attempts


def _invoke(dispatch_fn: Callable[..., str], prompt_text: str, model: str) -> str:
    """Call `dispatch_fn`, tolerating stubs that don't accept `model=`.

    Production fabric needs `model`; many test stubs only take `(prompt_text)`.
    We try the kwarg form first, fall back to positional on TypeError. Errors
    other than the signature mismatch propagate untouched.
    """
    try:
        return dispatch_fn(prompt_text, model=model)
    except TypeError:
        return dispatch_fn(prompt_text)
