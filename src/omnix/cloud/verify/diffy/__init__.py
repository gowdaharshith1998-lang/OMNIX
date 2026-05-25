"""Diffy-style multicast proxy with primary-vs-secondary noise filter.

Architecture:
  Each incoming HTTP request is forwarded to three upstreams concurrently:
    * primary    — the canonical (legacy) service
    * secondary  — a second instance of primary, used to fingerprint
                   non-deterministic noise
    * candidate  — the replicated (target) service

  Response returned to client = primary's response (Twitter Diffy pattern).
  Diffs:
    primary↔secondary  → "noise" channel (same legacy, expected to diverge
                         only on non-deterministic fields)
    candidate↔primary  → "candidate" channel; report after subtracting noise
"""

from __future__ import annotations

from omnix.cloud.verify.diffy.core import (  # noqa: F401
    DiffyProxy,
    DiffyReport,
    DiffyResult,
    NoiseFilter,
    semantic_diff,
)
