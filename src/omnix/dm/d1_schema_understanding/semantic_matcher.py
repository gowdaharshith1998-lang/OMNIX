"""Semantic matcher — Hungarian-optimal assignment of legacy ↔ target columns.

Pipeline:
  1. Compute pairwise cosine similarity between every legacy and every target
     ColumnContext using the embedder.
  2. Solve linear-sum-assignment to maximize total similarity.
  3. Apply thresholds:
       sim >= 0.85               → status="ok"
       0.60 <= sim < 0.85         → status="low_confidence", flagged for review
       max sim < 0.60             → status="no_match"
       N candidates above 0.60   → "ambiguous" if top-2 spread is < 0.05
  4. For every legacy column emit at least one ColumnMapping — never silently
     dropping any. Honesty invariant: the property test below enforces this.

Configuration:
  ``OMNIX_DM_CONFIDENCE_THRESHOLD`` env var overrides the 0.85 default.
"""

from __future__ import annotations

import os
from typing import List, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment

from omnix.dm._types import ColumnContext, ColumnMapping
from omnix.dm.d1_schema_understanding.column_embedder import embed

OK_THRESHOLD_DEFAULT = 0.85
LOW_CONFIDENCE_FLOOR = 0.60
AMBIGUITY_SPREAD = 0.05


def _ok_threshold() -> float:
    raw = os.environ.get("OMNIX_DM_CONFIDENCE_THRESHOLD")
    if raw is None:
        return OK_THRESHOLD_DEFAULT
    try:
        v = float(raw)
        if 0.0 < v < 1.0:
            return v
    except ValueError:
        pass
    return OK_THRESHOLD_DEFAULT


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def match(
    legacy_ctx: Tuple[ColumnContext, ...],
    target_ctx: Tuple[ColumnContext, ...],
) -> Tuple[ColumnMapping, ...]:
    """Return one ColumnMapping per legacy column.

    Contract (load-bearing for the honesty invariant):
      ``len(result) == len(legacy_ctx)`` — every legacy column appears in the
      output. The status field encodes whether the mapping is usable.
    """
    out: List[ColumnMapping] = []
    if not legacy_ctx:
        return tuple(out)

    if not target_ctx:
        for lc in legacy_ctx:
            out.append(
                ColumnMapping(
                    legacy_table=lc.table_name,
                    legacy_column=lc.column.name,
                    target_table=None,
                    target_column=None,
                    confidence=0.0,
                    status="no_match",
                    candidates=(),
                    rationale="no target schema provided",
                )
            )
        return tuple(out)

    # 1. compute all embeddings up-front (cached at the backend level)
    legacy_vecs = np.stack([embed(c) for c in legacy_ctx])
    target_vecs = np.stack([embed(c) for c in target_ctx])

    # 2. pairwise cosine similarity
    sim = np.zeros((len(legacy_ctx), len(target_ctx)), dtype=np.float64)
    ln = np.linalg.norm(legacy_vecs, axis=1)
    tn = np.linalg.norm(target_vecs, axis=1)
    ln[ln == 0.0] = 1.0
    tn[tn == 0.0] = 1.0
    sim = legacy_vecs @ target_vecs.T
    sim = sim / np.outer(ln, tn)

    # 3. Hungarian (maximize → negate for linear_sum_assignment which minimizes)
    n_legacy, n_target = sim.shape
    cost = -sim
    if n_legacy <= n_target:
        row_ind, col_ind = linear_sum_assignment(cost)
    else:
        # More legacy than target — pad with high cost so extra legacies fall
        # through to no_match.
        pad = np.full((n_legacy, n_legacy - n_target), 1e3)
        cost_padded = np.hstack([cost, pad])
        row_ind, col_ind = linear_sum_assignment(cost_padded)

    threshold = _ok_threshold()

    assigned_target: dict[int, int] = {int(r): int(c) for r, c in zip(row_ind, col_ind)}

    for li, lc in enumerate(legacy_ctx):
        # Build candidates list (top-3 by similarity)
        row_sims = sim[li, :]
        idxs = np.argsort(row_sims)[::-1][:3]
        candidates: List[Tuple[str, str, float]] = []
        for ti in idxs:
            ti = int(ti)
            tc = target_ctx[ti]
            candidates.append(
                (tc.table_name, tc.column.name, max(0.0, float(row_sims[ti])))
            )

        if li in assigned_target and assigned_target[li] < n_target:
            ti = assigned_target[li]
            tc = target_ctx[ti]
            best = float(sim[li, ti])
        else:
            tc = None
            ti = -1
            best = float(row_sims[idxs[0]]) if len(idxs) else 0.0
        # Cosine similarity is in [-1, 1]; confidence is in [0, 1]. Negative
        # similarity means "very dissimilar" — treat as 0 confidence.
        best = max(0.0, best)

        # Determine status
        if tc is None or best < LOW_CONFIDENCE_FLOOR:
            status = "no_match"
            target_table, target_column = None, None
            rationale = (
                f"best similarity {best:.3f} below floor {LOW_CONFIDENCE_FLOOR}"
            )
        else:
            target_table, target_column = tc.table_name, tc.column.name
            # Ambiguity check: are there other candidates within AMBIGUITY_SPREAD?
            sorted_sims = sorted(row_sims.tolist(), reverse=True)
            close = [s for s in sorted_sims[1:] if (best - s) < AMBIGUITY_SPREAD]
            if best >= threshold and not close:
                status = "ok"
                rationale = f"high-confidence semantic match ({best:.3f})"
            elif best >= LOW_CONFIDENCE_FLOOR and close:
                status = "ambiguous"
                rationale = (
                    f"top similarity {best:.3f} ties with {len(close)} alternates "
                    f"(spread<{AMBIGUITY_SPREAD})"
                )
            else:
                status = "low_confidence"
                rationale = (
                    f"similarity {best:.3f} below ok-threshold {threshold:.2f} "
                    "— operator review required"
                )

        out.append(
            ColumnMapping(
                legacy_table=lc.table_name,
                legacy_column=lc.column.name,
                target_table=target_table,
                target_column=target_column,
                confidence=best,
                status=status,
                candidates=tuple(candidates),
                rationale=rationale,
            )
        )

    if len(out) != len(legacy_ctx):
        raise AssertionError(
            "matcher invariant violated: output length != legacy length"
        )
    return tuple(out)


__all__ = [
    "OK_THRESHOLD_DEFAULT",
    "LOW_CONFIDENCE_FLOOR",
    "AMBIGUITY_SPREAD",
    "match",
]
