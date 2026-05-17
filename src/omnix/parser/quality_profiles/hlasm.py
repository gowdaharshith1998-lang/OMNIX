"""
HLASM (IBM high-level assembler) quality heuristic (stats from HLASM tree-sitter).

**Expected stat keys (all optional; default 0 / False):**

- ``n_csect_or_rsect`` (int) — *CSECT* / *RSECT* like section starts
- ``n_dsect_or_ltorg`` (int) — *DSECT* and *LTORG* occurrences
- ``n_instruction_statements`` (int) — machine/macro-executable statements (heuristic)
- ``n_macro_invocation`` (int) — macro call sites
- ``has_comments`` (bool) — significant comment text present
- ``n_using_or_drop`` (int) — *USING* / *DROP* pseudo-ops

**Scoring (additive, capped at 1.0):**

+0.30 if ≥1 CSECT/RSECT; +0.20 if ≥1 DSECT/LTORG; +0.20 if ≥5 instruction-like
statements; +0.15 if ≥1 macro invocation; +0.10 if comments present; +0.05 if
≥1 USING or DROP. Emphasizes object structure and then density.

**Target grammar:** `janus-llm/tree-sitter-ibmhlasm`.

**Known limitations:** Macro definition bodies and conditional assembly are only
partially captured for scoring. *USING* ranges may be implicit. This profile does
not import :mod:`omnix.parser.quality` or other profile modules.
"""

from __future__ import annotations

from typing import Any


def score(stats: dict[str, Any]) -> float:
    s = 0.0
    n_cr = int(stats.get("n_csect_or_rsect", 0) or 0)
    if n_cr >= 1:
        s += 0.30
    n_dlt = int(stats.get("n_dsect_or_ltorg", 0) or 0)
    if n_dlt >= 1:
        s += 0.20
    n_ins = int(stats.get("n_instruction_statements", 0) or 0)
    if n_ins >= 5:
        s += 0.20
    n_m = int(stats.get("n_macro_invocation", 0) or 0)
    if n_m >= 1:
        s += 0.15
    if _truthy(stats.get("has_comments")):
        s += 0.10
    n_ud = int(stats.get("n_using_or_drop", 0) or 0)
    if n_ud >= 1:
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
