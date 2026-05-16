"""
Fortran (modern) quality heuristic (stats from Fortran tree-sitter).

**Expected stat keys (all optional; default 0 / False):**

- ``n_program_or_module_or_sub_or_function`` (int) — top-level *PROGRAM*/*MODULE*/
  */SUBROUTINE*/*FUNCTION* units
- ``n_use`` (int) — *USE* statement count
- ``n_procedure_bodies`` (int) — non-trivial procedure / internal bodies
- ``has_implicit_none`` (bool) — *IMPLICIT NONE* present
- ``n_contains_or_interface`` (int) — *CONTAINS* and *INTERFACE* block count
- ``n_lines`` (int) — line count in file (nontrivial: ``> 10``)

**Scoring (additive, capped at 1.0):**

+0.25 if ≥1 program/module/proc/function unit; +0.20 if ≥1 *USE*; +0.20 if ≥1
procedure body; +0.15 if *IMPLICIT NONE*; +0.10 if ≥1 *CONTAINS* or *INTERFACE*;
+0.10 if *n_lines* is greater than 10. Encourages modular, explicit Fortran over stubs.

**Target grammar:** `stadelmanma/tree-sitter-fortran` (roughly 50% coverage of the
full language; sufficient for many scientific codebases).

**Known limitations:** C preprocessor blocks, `INCLUDE`, and some vendor extensions
are weakly or not modeled. Coarray / F2008+ features have incomplete coverage.
This profile does not import :mod:`omnix.parser.quality` or other profile modules.
"""

from __future__ import annotations

from typing import Any


def score(stats: dict[str, Any]) -> float:
    s = 0.0
    n_top = int(stats.get("n_program_or_module_or_sub_or_function", 0) or 0)
    if n_top >= 1:
        s += 0.25
    n_use = int(stats.get("n_use", 0) or 0)
    if n_use >= 1:
        s += 0.20
    n_pb = int(stats.get("n_procedure_bodies", 0) or 0)
    if n_pb >= 1:
        s += 0.20
    if _truthy(stats.get("has_implicit_none")):
        s += 0.15
    n_ci = int(stats.get("n_contains_or_interface", 0) or 0)
    if n_ci >= 1:
        s += 0.10
    n_lines = int(stats.get("n_lines", 0) or 0)
    if n_lines > 10:
        s += 0.10
    return round(min(1.0, s), 4)


def _truthy(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return bool(v)
