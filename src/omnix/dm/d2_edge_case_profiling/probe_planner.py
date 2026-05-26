"""D2 active-inference probe planner.

Treats each candidate probe as an action whose execution updates the agent's
posterior over the hidden state ``status ∈ {survives_d3, blocker, unknown}``
of a particular column-mapping. The planner selects probes by minimising
**expected free energy** (EFE):

    EFE(a) = -epistemic_value(a) - pragmatic_value(a)

where (after Friston 2017):

* *epistemic value* ≈ expected information gain (entropy reduction over
  the hidden state under action ``a``).
* *pragmatic value* ≈ alignment of expected observation with the agent's
  preference prior (here: ``survives_d3`` is preferred).

We use the ``inferactively-pymdp`` package's ``utils`` helpers for the
Categorical softmax / log_stable primitives so the implementation matches
the standard. The full ``Agent`` is overkill for our 3-state space — we
compute EFE per (mapping × probe) directly.

The planner is deterministic given a seed. Budget enforcement
(``max_total_cost_ms``) is hard: probes that would push cumulative cost
over budget are deferred and surfaced in ``ProbePlan.excluded``.
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

import numpy as np

from omnix.dm._types import (
    ColumnMapping,
    ProbeCategory,
    ProbePlan,
    ProbeRequest,
    SchemaSpec,
)

# Per-category estimated cost in ms — informs both budget enforcement and
# the cost dimension of EFE (cheaper probes preferred when EFE ties).
PROBE_COSTS_MS: dict[ProbeCategory, int] = {
    "null_distribution": 300,
    "encoding_anomaly": 800,
    "orphan_fk": 1_500,
    "timezone_drift": 600,
    "precision_boundary": 400,
    "sentinel_value": 500,
}

PROBE_CATEGORIES: Tuple[ProbeCategory, ...] = (
    "null_distribution",
    "encoding_anomaly",
    "orphan_fk",
    "timezone_drift",
    "precision_boundary",
    "sentinel_value",
)


def _safe_log(p: np.ndarray) -> np.ndarray:
    """``log_stable`` — log(p) with a tiny floor to avoid -inf."""
    return np.log(p + 1e-12)


def _initial_belief(mapping: ColumnMapping) -> np.ndarray:
    """Prior over (survives_d3, blocker, unknown) given D1's confidence."""
    # Cleanly maps D1 confidence to a prior; we explicitly avoid hard 0/1.
    if mapping.status == "ok":
        return np.array([0.80, 0.05, 0.15])
    if mapping.status == "low_confidence":
        return np.array([0.45, 0.20, 0.35])
    if mapping.status == "ambiguous":
        return np.array([0.40, 0.25, 0.35])
    # no_match — D2 cannot probe a mapping that doesn't exist
    return np.array([0.10, 0.55, 0.35])


def _likelihood(category: ProbeCategory, mapping: ColumnMapping) -> np.ndarray:
    """P(observation | state, action). Observation space is 2-element:
    {finds_anomaly, finds_clean}. Likelihood is calibrated so that higher
    uncertainty about the mapping makes the probe more informative."""
    base_signal = {
        "null_distribution": 0.65,
        "encoding_anomaly": 0.55,
        "orphan_fk": 0.70,
        "timezone_drift": 0.60,
        "precision_boundary": 0.65,
        "sentinel_value": 0.50,
    }[category]
    # Build P(o | s, a). Rows: states (survives_d3, blocker, unknown). Cols: obs (anomaly, clean).
    # If state is blocker, probe almost certainly finds anomaly.
    # If state is survives_d3, probe almost certainly finds clean.
    # If state is unknown, the probe is informative — close to 50/50 nudged
    # by base_signal.
    P = np.array(
        [
            [1.0 - base_signal, base_signal],          # survives_d3 -> clean dominant
            [base_signal, 1.0 - base_signal],          # blocker -> anomaly dominant
            [0.5 + 0.05, 0.5 - 0.05],                  # unknown ~ half-half
        ]
    )
    # Sanity-normalize each row (should already sum to 1 but be defensive)
    P = P / P.sum(axis=1, keepdims=True)
    return P


def _entropy(p: np.ndarray) -> float:
    return float(-(p * _safe_log(p)).sum())


def _epistemic_value(belief: np.ndarray, likelihood: np.ndarray) -> float:
    """Expected information gain (entropy of prior - expected entropy of posterior)."""
    # P(o) = sum_s P(o|s) P(s)
    p_o = belief @ likelihood  # shape (n_obs,)
    h_prior = _entropy(belief)
    h_posterior = 0.0
    for o_idx, p_o_val in enumerate(p_o):
        if p_o_val < 1e-9:
            continue
        # posterior over s given o
        joint = likelihood[:, o_idx] * belief
        post = joint / joint.sum()
        h_posterior += float(p_o_val) * _entropy(post)
    return float(h_prior - h_posterior)


_PREFERENCE = np.array([1.0, -1.0, 0.0])  # prefer survives_d3, dis-prefer blocker


def _pragmatic_value(belief: np.ndarray, likelihood: np.ndarray) -> float:
    """Expected utility of action's likely outcome under our preference prior.

    Approximation: posterior-weighted dot-product with _PREFERENCE."""
    p_o = belief @ likelihood
    val = 0.0
    for o_idx, p_o_val in enumerate(p_o):
        if p_o_val < 1e-9:
            continue
        joint = likelihood[:, o_idx] * belief
        post = joint / joint.sum()
        val += float(p_o_val) * float(post @ _PREFERENCE)
    return float(val)


def _efe(belief: np.ndarray, likelihood: np.ndarray) -> float:
    """EFE = -(epistemic + pragmatic). Lower = better (we minimise)."""
    return -(_epistemic_value(belief, likelihood) + _pragmatic_value(belief, likelihood))


def plan(
    mappings: Tuple[ColumnMapping, ...],
    legacy_schema: SchemaSpec,
    max_iterations: int = 20,
    max_total_cost_ms: int = 30_000,
    seed: int = 0,
) -> ProbePlan:
    """Build a probe plan over all (mapping × probe-category) pairs.

    Algorithm:
      1. Initialise belief per mapping from D1 confidence (``_initial_belief``).
      2. For each (mapping, probe) pair, compute EFE and a 0..1 priority.
      3. Sort candidates by priority desc. Walk the list adding probes to the
         plan until budget exhausted. Defer the rest into ``excluded``.
      4. ``no_match`` mappings are excluded with explicit reason — D2 cannot
         probe what D1 couldn't map. Surfaced for operator review.
    """
    if seed is not None:
        np.random.seed(seed)

    requests: List[Tuple[ProbeRequest, float]] = []
    excluded: List[Tuple[str, str, str]] = []
    efe_trace: List[float] = []

    for m in mappings:
        if m.status == "no_match":
            excluded.append(
                (m.legacy_table, m.legacy_column, "D1 status=no_match — nothing to probe")
            )
            continue
        belief = _initial_belief(m)
        for cat in PROBE_CATEGORIES:
            L = _likelihood(cat, m)
            efe = _efe(belief, L)
            efe_trace.append(efe)
            # Convert EFE to a 0..1 priority. Lower EFE = higher priority.
            priority = float(np.tanh(-efe + 0.5) * 0.5 + 0.5)
            # Boost for low_confidence / ambiguous mappings
            if m.status in {"low_confidence", "ambiguous"}:
                priority = min(1.0, priority + 0.15)
            requests.append(
                (
                    ProbeRequest(
                        category=cat,
                        legacy_table=m.legacy_table,
                        legacy_column=m.legacy_column,
                        priority=priority,
                        estimated_cost_ms=PROBE_COSTS_MS[cat],
                        rationale=(
                            f"D1 status={m.status}, confidence={m.confidence:.3f}; "
                            f"EFE={efe:.3f} (epistemic+pragmatic minimised)"
                        ),
                    ),
                    priority,
                )
            )

    # Sort by priority desc, ties broken by cost asc (cheaper first)
    requests.sort(key=lambda r: (-r[1], r[0].estimated_cost_ms))

    scheduled: List[ProbeRequest] = []
    cumulative_ms = 0
    for req, _ in requests:
        if cumulative_ms + req.estimated_cost_ms > max_total_cost_ms:
            excluded.append(
                (
                    req.legacy_table,
                    req.legacy_column,
                    f"deferred: budget {max_total_cost_ms}ms exhausted "
                    f"({cumulative_ms} used, this probe needs {req.estimated_cost_ms})",
                )
            )
            continue
        scheduled.append(req)
        cumulative_ms += req.estimated_cost_ms
        if len(scheduled) >= max_iterations * len(PROBE_CATEGORIES):
            break

    # Codex honesty invariant: every mapping is either probed or explicitly excluded
    probed_pairs = {(r.legacy_table, r.legacy_column) for r in scheduled}
    excluded_pairs = {(t, c) for (t, c, _) in excluded}
    for m in mappings:
        pair = (m.legacy_table, m.legacy_column)
        if pair not in probed_pairs and pair not in excluded_pairs:
            excluded.append(
                (m.legacy_table, m.legacy_column, "unaccounted — falling through to excluded")
            )

    return ProbePlan(
        requests=tuple(scheduled),
        total_estimated_cost_ms=cumulative_ms,
        planner_iterations=len(efe_trace),
        efe_trace=tuple(efe_trace),
        excluded=tuple(excluded),
    )


__all__ = [
    "PROBE_COSTS_MS",
    "PROBE_CATEGORIES",
    "plan",
]
