"""Daikon-lite — dynamic invariant detection (May 2026 Gopinath pattern).

We observe variable snapshots at program points (entry / exit) and mine:
  - constant         x == c
  - non-zero         x != 0
  - non-negative     x >= 0
  - non-positive     x <= 0
  - small range      a <= x <= b  (for integers, when |b-a| < 32)
  - linear           x = a*y + b  (for pairs of int/float vars, conf >= 0.99)
  - ordering         x < y, x <= y, x == y
  - sortedness       array is monotonically non-decreasing
  - non-empty        array is always non-empty
  - all-positive     all elements of array are > 0

Compare-mode: the same miner runs on the legacy and candidate traces;
invariants that hold on legacy but not on candidate are equivalence failures.
"""

from __future__ import annotations

from omnix.cloud.verify.daikon_lite.miner import (  # noqa: F401
    Invariant,
    InvariantSet,
    ProgramPoint,
    Snapshot,
    Tracer,
    compare,
    mine,
)
