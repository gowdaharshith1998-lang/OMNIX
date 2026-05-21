from __future__ import annotations

from omnix.provenance.sidecar import build_sidecar
from omnix.retrieval.token_packer import PackedBundle
from omnix.traversal.agent_loop import TraversalResult


def test_sidecar_shape_required_keys() -> None:
    sidecar = build_sidecar(
        "HELLO",
        PackedBundle([("n1", "text")], [], 1, {"bm25": 1}),
        TraversalResult(PackedBundle([], [], 0), [], 0, None),
        [],
        "e" * 64,
        {"retrieval": 1},
    )
    assert sidecar["schema_version"] == "omnix.provenance.v1"
    assert "subgraph_fingerprint" in sidecar
