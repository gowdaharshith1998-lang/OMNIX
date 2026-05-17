"""M1 rebuild runner — walks the graph, dispatches LLM calls, runs gates
1-4 mechanically, signs + writes one RebuildReceipt per node.

Output layout:

    <project_path>/.omnix/receipts/rebuilds/<timestamp>/
        <node_fqn>.java   — the LLM's rebuilt source
        <node_fqn>.json   — RebuildReceipt canonical JSON
        <node_fqn>.sig    — base64 Ed25519 signature of the JSON's canonical bytes

`<timestamp>` is UTC ISO-8601 with `:` replaced by `-` so the filesystem
is happy on every OS. `<node_fqn>` slashes / colons are replaced with `_`
for the same reason.

The `dispatch_fn` boundary mirrors `omnix.orchestrator.dispatcher.run` —
tests inject a stub; production defaults to
`omnix.orchestrator.dispatcher._default_dispatch_fn` (vault-credentialed).
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from omnix.orchestrator.attempt import sha256_hex
from omnix.orchestrator.dispatcher import (
    OrchestratorError,
    _collect_graph_inputs,
    _default_dispatch_fn,
    _load_graph,
    _load_source,
)
from omnix.orchestrator.prompt_template import PROMPT_TEMPLATE_VERSION, format_prompt
from omnix.orchestrator.topological import topo_sort
from omnix.receipts.finding_receipt import (
    compute_project_id,
    now_iso8601_utc,
)
from omnix.receipts.rebuild_receipt import (
    GATE_NAMES,
    GateResult,
    RebuildReceipt,
    default_m2_deferred_gate_results,
    sha256_hex_text,
    sign_rebuild,
)
from omnix.semantic import SemanticNode
from omnix.spec.generator import generate as _generate_spec


@dataclass(frozen=True)
class RebuildOutput:
    """One node's rebuild outputs on disk."""

    node_fqn: str
    receipt_path: Path
    signature_path: Path
    rebuilt_source_path: Path


_FS_SAFE = str.maketrans({"/": "_", ":": "_", "\\": "_", " ": "_"})


def _safe(fqn: str) -> str:
    """Filesystem-safe form of an FQN."""
    return fqn.translate(_FS_SAFE)


def _timestamp_dir_name() -> str:
    return now_iso8601_utc().replace(":", "-")


def _omnix_version() -> str:
    try:
        from omnix.omnix_version import __version__ as v
    except Exception:  # pragma: no cover — version module is always present
        return "0.0.0"
    return str(v)


def _run_gates_1_to_4(
    *,
    spec: Any,
    rebuilt_source: str,
) -> tuple[GateResult, ...]:
    """Mechanically run gates 1-4 against a rebuilt source + spec.

    Each gate returns either `None` (passed) or a `GateError`-shaped dict
    with `details`. We translate that into a `GateResult` with a `passed`
    or `failed` status.
    """
    from omnix.gates import gate1_syntactic, gate2_typecheck, gate3_signature

    results: list[GateResult] = []

    err = gate1_syntactic.check(rebuilt_source)
    results.append(
        GateResult(
            gate_number=1,
            gate_name=GATE_NAMES[1],
            status="passed" if err is None else "failed",
            details={} if err is None else dict(err.details),
        )
    )

    err = gate2_typecheck.check(rebuilt_source)
    results.append(
        GateResult(
            gate_number=2,
            gate_name=GATE_NAMES[2],
            status="passed" if err is None else "failed",
            details={} if err is None else dict(err.details),
        )
    )

    err = gate3_signature.check(rebuilt_source, spec.signature)
    results.append(
        GateResult(
            gate_number=3,
            gate_name=GATE_NAMES[3],
            status="passed" if err is None else "failed",
            details={} if err is None else dict(err.details),
        )
    )

    # Gate 4 (dependency) is a M1 placeholder — gate runner module exists
    # but the mechanical dep-check is not implemented in this slice.
    # Emit "skipped" rather than fake a pass.
    results.append(
        GateResult(
            gate_number=4,
            gate_name=GATE_NAMES[4],
            status="skipped",
            details={
                "reason": (
                    "Gate 4 (dependency) mechanical check is M1-phase-6 "
                    "follow-up scope. Status 'skipped' — neither passed "
                    "nor failed. Distinct from gates 5+6 which are "
                    "M2-deferred."
                )
            },
        )
    )

    return tuple(results)


def _build_receipt(
    *,
    project_id: str,
    node: SemanticNode,
    target_language: str,
    legacy_source: str,
    rebuilt_source: str,
    spec: Any,
    prompt_text_hash: str,
    model: str,
    gate_results_1_to_4: tuple[GateResult, ...],
) -> RebuildReceipt:
    full_gates = gate_results_1_to_4 + default_m2_deferred_gate_results()
    return RebuildReceipt(
        project_id=project_id,
        node_fqn=node.fqn,
        target_language=target_language,
        legacy_source_sha256=sha256_hex_text(legacy_source),
        rebuilt_source_sha256=sha256_hex_text(rebuilt_source),
        spec_hash=sha256_hex(spec.to_json()),
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        prompt_text_hash=prompt_text_hash,
        model=model,
        gate_results=full_gates,
        timestamp=now_iso8601_utc(),
        omnix_version=_omnix_version(),
    )


def _write_outputs(
    *,
    out_dir: Path,
    node_fqn: str,
    rebuilt_source: str,
    receipt: RebuildReceipt,
    signature_b64: str,
) -> RebuildOutput:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = _safe(node_fqn)
    src_path = out_dir / f"{base}.java"
    receipt_path = out_dir / f"{base}.json"
    sig_path = out_dir / f"{base}.sig"

    src_path.write_text(rebuilt_source, encoding="utf-8")
    receipt_path.write_bytes(receipt.canonical_json())
    sig_path.write_text(signature_b64 + "\n", encoding="utf-8")

    return RebuildOutput(
        node_fqn=node_fqn,
        receipt_path=receipt_path,
        signature_path=sig_path,
        rebuilt_source_path=src_path,
    )


def run(
    project_path: Path,
    *,
    target_language: str = "java21",
    node_filter: str | None = None,
    dispatch_fn: Callable[..., str] | None = None,
    model: str = "claude-opus-4.7",
    output_root: Path | None = None,
) -> list[RebuildOutput]:
    """Walk the graph and emit one signed RebuildReceipt per matched node.

    Args:
        project_path: project root containing `.omnix/omnix.db`.
        target_language: spec target (M1 supports only "java21").
        node_filter: optional fnmatch pattern (e.g. "*StringUtils.reverse")
            applied to `node.fqn`. None = all nodes.
        dispatch_fn: (prompt_text, *, model) -> str seam. Defaults to the
            credentialed fabric path (vault required).
        model: requested model identifier.
        output_root: optional override for the receipts directory; defaults
            to `<project_path>/.omnix/receipts/rebuilds/<timestamp>/`.

    Returns the list of RebuildOutput records (one per processed node) in
    dispatch order.
    """
    graph = _load_graph(project_path)
    return _run_with_graph(
        graph=graph,
        project_path=project_path,
        target_language=target_language,
        node_filter=node_filter,
        dispatch_fn=dispatch_fn,
        model=model,
        output_root=output_root,
    )


def _run_with_graph(
    *,
    graph: Any,
    project_path: Path,
    target_language: str,
    node_filter: str | None,
    dispatch_fn: Callable[..., str] | None,
    model: str,
    output_root: Path | None,
) -> list[RebuildOutput]:
    """Inner loop — split out so tests can inject a fully-stubbed graph."""
    effective_dispatch = dispatch_fn if dispatch_fn is not None else _default_dispatch_fn

    nodes, edges, fqn_index = _collect_graph_inputs(graph)
    if node_filter is not None:
        nodes = [n for n in nodes if fnmatch.fnmatchcase(n.fqn, node_filter)]
        if not nodes:
            raise OrchestratorError(
                f"node_filter {node_filter!r} matched zero nodes; check the pattern"
            )
        fqn_index = {n.fqn: n for n in nodes}
        edges = [(s, d) for s, d in edges if s in fqn_index and d in fqn_index]

    order = topo_sort([n.fqn for n in nodes], edges)
    project_id = compute_project_id(project_path)

    if output_root is None:
        out_dir = (
            project_path
            / ".omnix"
            / "receipts"
            / "rebuilds"
            / _timestamp_dir_name()
        )
    else:
        out_dir = output_root

    outputs: list[RebuildOutput] = []
    for entry in order:
        # SCC nodes are returned as a list — for M1 v1, treat each member
        # independently with its own prompt; receipts batch is M2 scope.
        node_fqns = entry if isinstance(entry, list) else [entry]
        for fqn in node_fqns:
            node = fqn_index[fqn]
            legacy_source = _load_source(node, project_path)
            spec = _generate_spec(node, graph, target_language)
            prompt_text, prompt_hash = format_prompt(spec, legacy_source)
            rebuilt_source = _invoke(effective_dispatch, prompt_text, model)

            gates_1_to_4 = _run_gates_1_to_4(spec=spec, rebuilt_source=rebuilt_source)
            receipt = _build_receipt(
                project_id=project_id,
                node=node,
                target_language=target_language,
                legacy_source=legacy_source,
                rebuilt_source=rebuilt_source,
                spec=spec,
                prompt_text_hash=prompt_hash,
                model=model,
                gate_results_1_to_4=gates_1_to_4,
            )
            signature_b64 = sign_rebuild(receipt)
            outputs.append(
                _write_outputs(
                    out_dir=out_dir,
                    node_fqn=fqn,
                    rebuilt_source=rebuilt_source,
                    receipt=receipt,
                    signature_b64=signature_b64,
                )
            )
    return outputs


def _invoke(dispatch_fn: Callable[..., str], prompt_text: str, model: str) -> str:
    """Tolerate stubs that don't accept the `model` kwarg."""
    try:
        return dispatch_fn(prompt_text, model=model)
    except TypeError:
        return dispatch_fn(prompt_text)
