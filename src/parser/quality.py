"""Heuristic graph quality score (0.0–1.0) for LLM fallback gating (Layer 3 uses thresholds)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class QualityInputs:
    n_functions: int
    n_classes: int
    n_imports: int
    n_call_edges: int
    n_lines: int
    function_class_names: tuple[str, ...]


def _name_looks_synthetic(n: str) -> bool:
    t = n.strip()
    if not t:
        return True
    if t.startswith("anonymous_"):
        return True
    if re.match(r"^node_\d+$", t):
        return True
    return False


def compute_score(i: QualityInputs) -> float:
    """
    0.0 if no functions, classes, or imports; otherwise additive components
    capping at 1.0.
    """
    if i.n_functions == 0 and i.n_classes == 0 and i.n_imports == 0:
        return 0.0
    score = 0.0
    if i.n_functions >= 1:
        score += 0.3
    if i.n_call_edges >= 1:
        score += 0.2
    if i.n_imports >= 1:
        score += 0.2
    names = [x for x in i.function_class_names if x and not _name_looks_synthetic(x)]
    if names:
        score += 0.2
    if i.n_lines > 10 and i.n_lines > 0 and i.n_functions > 0:
        density = i.n_functions / i.n_lines
        if density > 0.05:
            score += 0.1
    return round(min(1.0, score), 4)
