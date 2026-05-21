"""Canonical subgraph fingerprints."""

from __future__ import annotations

import json
from collections.abc import Iterable
from hashlib import sha256


def canonical_subgraph_fingerprint(node_ids: Iterable[str], edge_ids: Iterable[str]) -> str:
    payload = {"nodes": sorted(str(n) for n in node_ids), "edges": sorted(str(e) for e in edge_ids)}
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return sha256(data).hexdigest()
