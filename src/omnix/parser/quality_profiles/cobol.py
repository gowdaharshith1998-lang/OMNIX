"""
COBOL graph-quality heuristic (stats dict from the COBOL tree-sitter ingest layer).

**Expected stat keys (all optional; default falsy/0):**

- ``has_identification_division`` (bool) — *IDENTIFICATION DIVISION* present
- ``has_data_division`` (bool) — *DATA DIVISION* present
- ``has_procedure_division`` (bool) — *PROCEDURE DIVISION* / main division
- ``n_paragraphs_in_procedure`` (int) — count of paragraph headers under procedure
- ``n_perform_or_call`` (int) — *PERFORM* and external *CALL* statement count
- ``has_linkage_or_copybook`` (bool) — *LINKAGE SECTION* and/or *COPY* usage

**Scoring (additive, capped at 1.0):**

+0.20 *IDENTIFICATION DIVISION*; +0.20 *DATA*; +0.30 *PROCEDURE*; +0.15 if
≥1 procedure paragraph; +0.10 if ≥1 *PERFORM* or *CALL*; +0.05 if linkage / copy
references. Rewards recognizable program structure before deep analysis.

**Target grammar:** `yutaro-sakamoto/tree-sitter-cobol` (COBOL-85 style).

**Known limitations:** Dialects beyond COBOL85 are untested. Copybooks and generated
procedural glue may be under-counted. Macro-like preprocessors are not modeled.
This profile does not import :mod:`omnix.parser.quality` or other profile modules.
"""


from __future__ import annotations

from typing import Any


def score(stats: dict[str, Any]) -> float:
    s = 0.0
    if _truthy(stats.get("has_identification_division")):
        s += 0.20
    if _truthy(stats.get("has_data_division")):
        s += 0.20
    if _truthy(stats.get("has_procedure_division")):
        s += 0.30
    n_para = int(stats.get("n_paragraphs_in_procedure", 0) or 0)
    if n_para >= 1:
        s += 0.15
    n_call = int(stats.get("n_perform_or_call", 0) or 0)
    if n_call >= 1:
        s += 0.10
    if _truthy(stats.get("has_linkage_or_copybook")):
        s += 0.05
    return round(min(1.0, s), 4)


def _truthy(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return bool(v)
