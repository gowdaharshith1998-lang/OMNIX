from __future__ import annotations

from omnix.provenance.fingerprint import canonical_subgraph_fingerprint


def test_fingerprint_deterministic_and_sensitive() -> None:
    a = canonical_subgraph_fingerprint(["b", "a"], ["2", "1"])
    b = canonical_subgraph_fingerprint(["a", "b"], ["1", "2"])
    c = canonical_subgraph_fingerprint(["a"], ["1", "2"])
    assert a == b
    assert a != c
