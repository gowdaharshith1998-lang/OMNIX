"""CutoverProposal emitter — sustained-window parity check, signed proposal.

PR C ships the structural shape: ``parity_metrics`` is populated by PR D's
row-diff gate (G7). Without PR D, we emit metrics with
``divergence_rate=0.0`` and a ``recommended_action="wait_longer"`` note so
the operator can correlate against the row-diff data once PR D lands.
"""

from __future__ import annotations

import datetime
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from jsonschema import Draft202012Validator

from omnix.crypto import ml_dsa_65
from omnix.dm._types import CutoverProposal, LagReport, ParityMetric
from omnix.dm.receipts.ml_dsa_65_signer import sign_canonical
from omnix.dm.receipts.schemas import CUTOVER_PROPOSAL_SCHEMA


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _atomic_write(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)


_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class CutoverState:
    """State machine: tracks sustained-window start across ticks."""

    sustained_window_start: Optional[float] = None  # monotonic seconds
    parity_threshold: float = 0.0001
    sustained_window_required_sec: int = 900


def evaluate(
    *,
    state: CutoverState,
    lag_report: LagReport,
    parity_metrics: Sequence[ParityMetric] = (),
    now_monotonic: Optional[float] = None,
) -> Optional[CutoverProposal]:
    """Evaluate the latest lag report + parity metrics. Returns a
    :class:`CutoverProposal` only when:
      * lag is finite and ≤ threshold (we use lag_seconds < 60 by default), AND
      * every parity metric's divergence_rate ≤ ``state.parity_threshold``, AND
      * the sustained-window has elapsed.

    Otherwise returns ``None``. When parity is high (any metric exceeds the
    threshold), returns a proposal with ``parity_not_met=True`` and
    ``recommended_action="investigate_divergence"`` — honest signal that the
    operator should look into divergence, not auto-cut over.
    """
    now = now_monotonic if now_monotonic is not None else time.monotonic()

    lag_ok = (
        lag_report.lag_estimated_seconds is not None
        and lag_report.lag_estimated_seconds < 60.0
        and not lag_report.legacy_unreachable
        and not lag_report.target_unreachable
    )

    parity_failures = [
        m for m in parity_metrics if m.divergence_rate > state.parity_threshold
    ]
    if parity_failures:
        return CutoverProposal(
            migration_id=lag_report.migration_id,
            timestamp=_utcnow_iso(),
            predecessor_hash="0" * 64,  # caller will overwrite via emit_proposal
            sustained_window_seconds=int(
                now - (state.sustained_window_start or now)
            ),
            measured_lag_seconds=lag_report.lag_estimated_seconds or 0.0,
            parity_threshold=state.parity_threshold,
            parity_metrics=tuple(parity_metrics),
            parity_not_met=True,
            recommended_action="investigate_divergence",
        )

    if not lag_ok:
        state.sustained_window_start = None
        return None

    if state.sustained_window_start is None:
        state.sustained_window_start = now
        return None

    elapsed = now - state.sustained_window_start
    if elapsed < state.sustained_window_required_sec:
        return None

    return CutoverProposal(
        migration_id=lag_report.migration_id,
        timestamp=_utcnow_iso(),
        predecessor_hash="0" * 64,  # caller overwrites
        sustained_window_seconds=int(elapsed),
        measured_lag_seconds=lag_report.lag_estimated_seconds or 0.0,
        parity_threshold=state.parity_threshold,
        parity_metrics=tuple(parity_metrics),
        parity_not_met=False,
        recommended_action="operator_sign",
    )


def emit_proposal(
    proposal: CutoverProposal,
    *,
    predecessor_hash: str,
    secret_key: bytes,
    public_key: bytes,
    output_root: Path,
) -> Path:
    if not _HASH_RE.match(predecessor_hash):
        raise ValueError(
            f"predecessor_hash must be 64-char hex, got {predecessor_hash!r}"
        )
    payload = {
        "schema_version": "omnix-dm/cutover-proposal/v1",
        "migration_id": proposal.migration_id,
        "timestamp": proposal.timestamp,
        "predecessor_hash": predecessor_hash,
        "sustained_window_seconds": proposal.sustained_window_seconds,
        "measured_lag_seconds": round(proposal.measured_lag_seconds, 6),
        "parity_threshold": proposal.parity_threshold,
        "parity_metrics": [
            {
                "table": m.table,
                "rows_compared": m.rows_compared,
                "rows_diverged": m.rows_diverged,
                "divergence_rate": round(m.divergence_rate, 9),
            }
            for m in proposal.parity_metrics
        ],
        "parity_not_met": proposal.parity_not_met,
        "recommended_action": proposal.recommended_action,
        "operator_signoff": proposal.operator_signoff,
        "signing_algorithm": "ML-DSA-65",
        "public_key_fingerprint": ml_dsa_65.fingerprint(public_key),
    }
    Draft202012Validator(CUTOVER_PROPOSAL_SCHEMA).validate(payload)
    canonical, sig_hex = sign_canonical(payload, secret_key)
    out_dir = Path(output_root) / proposal.migration_id / "d5"
    safe_ts = proposal.timestamp.replace(":", "-")
    json_path = out_dir / f"cutover-proposal-{safe_ts}.json"
    sig_path = out_dir / f"cutover-proposal-{safe_ts}.json.sig"
    _atomic_write(json_path, canonical)
    _atomic_write(sig_path, sig_hex.encode("ascii"))
    return json_path


__all__ = ["CutoverState", "evaluate", "emit_proposal"]
