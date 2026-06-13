"""Lag monitor — periodic LagReport emission, sustained-window state machine.

Lag computation is intentionally simple in PR C: ``lag_lsn_bytes = legacy_lsn -
target_applied_lsn`` (as 64-bit ints). The estimated-seconds field is a hint
based on a configurable byte-rate; operators can tune via env.

Health honesty: ``legacy_unreachable=True`` whenever the legacy query for the
current LSN fails. The report is still written (signed) so the audit trail
captures the outage moment instead of going silent.
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from jsonschema import Draft202012Validator

from omnix.crypto import ml_dsa_65
from omnix.dm._types import LagReport
from omnix.dm.d5_change_data_capture.cdc_replayer import CDCReplayState
from omnix.dm.receipts.ml_dsa_65_signer import sign_canonical
from omnix.dm.receipts.schemas import LAG_REPORT_SCHEMA


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _hash_lsn(lsn: str) -> int:
    if "/" not in lsn:
        return 0
    hi, lo = lsn.split("/", 1)
    try:
        return (int(hi, 16) << 32) | int(lo, 16)
    except ValueError:
        return 0


def _atomic_write(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)


@dataclass
class LagMonitorState:
    """In-process tracking the lag monitor uses across ticks."""

    last_event_count: int = 0
    last_quar_count: int = 0
    sustained_window_start: Optional[float] = None  # monotonic seconds
    last_unhandled_seen: List[str] = field(default_factory=list)


class LagMonitor:
    """Tick once per interval; emit a signed LagReport each tick."""

    def __init__(
        self,
        *,
        migration_id: str,
        replay_state: CDCReplayState,
        output_root: Path,
        secret_key: bytes,
        public_key: bytes,
        legacy_lsn_provider: Callable[[], Optional[str]],
        target_lsn_provider: Callable[[], Optional[str]],
        bytes_per_second_estimate: float = 1_000_000.0,
    ):
        self.migration_id = migration_id
        self.replay_state = replay_state
        self.output_root = Path(output_root)
        self.secret_key = secret_key
        self.public_key = public_key
        self.legacy_lsn_provider = legacy_lsn_provider
        self.target_lsn_provider = target_lsn_provider
        self.bytes_per_second_estimate = bytes_per_second_estimate
        self.state = LagMonitorState()

    def tick(self) -> LagReport:
        legacy_unreachable = False
        target_unreachable = False
        try:
            legacy_lsn = self.legacy_lsn_provider()
        except Exception:
            legacy_lsn = None
            legacy_unreachable = True
        try:
            target_lsn = self.target_lsn_provider()
        except Exception:
            target_lsn = None
            target_unreachable = True

        lag_bytes: Optional[int] = None
        lag_seconds: Optional[float] = None
        if (
            not legacy_unreachable
            and not target_unreachable
            and legacy_lsn is not None
            and target_lsn is not None
        ):
            lag_bytes = max(0, _hash_lsn(legacy_lsn) - _hash_lsn(target_lsn))
            lag_seconds = (
                lag_bytes / self.bytes_per_second_estimate
                if self.bytes_per_second_estimate > 0
                else None
            )

        events_now = self.replay_state.events_replayed
        quar_now = self.replay_state.events_quarantined
        interval_events = max(0, events_now - self.state.last_event_count)
        interval_quar = max(0, quar_now - self.state.last_quar_count)
        self.state.last_event_count = events_now
        self.state.last_quar_count = quar_now

        # Accumulate unhandled event types monotonically.
        for ut in self.replay_state.unhandled_event_types:
            if ut not in self.state.last_unhandled_seen:
                self.state.last_unhandled_seen.append(ut)

        report = LagReport(
            migration_id=self.migration_id,
            timestamp=_utcnow_iso(),
            legacy_current_lsn=legacy_lsn,
            target_applied_lsn=target_lsn,
            legacy_unreachable=legacy_unreachable,
            target_unreachable=target_unreachable,
            lag_lsn_bytes=lag_bytes,
            lag_estimated_seconds=lag_seconds,
            events_replayed_last_interval=interval_events,
            events_quarantined_last_interval=interval_quar,
            unhandled_event_types_seen=tuple(self.state.last_unhandled_seen),
        )
        self._write_report(report)
        return report

    def _write_report(self, report: LagReport) -> Path:
        payload = {
            "schema_version": "omnix-dm/lag-report/v1",
            "migration_id": report.migration_id,
            "timestamp": report.timestamp,
            "legacy_current_lsn": report.legacy_current_lsn,
            "target_applied_lsn": report.target_applied_lsn,
            "legacy_unreachable": report.legacy_unreachable,
            "target_unreachable": report.target_unreachable,
            "lag_lsn_bytes": report.lag_lsn_bytes,
            "lag_estimated_seconds": (
                round(report.lag_estimated_seconds, 6)
                if report.lag_estimated_seconds is not None
                else None
            ),
            "events_replayed_last_interval": report.events_replayed_last_interval,
            "events_quarantined_last_interval": report.events_quarantined_last_interval,
            "unhandled_event_types_seen": list(report.unhandled_event_types_seen),
            "signing_algorithm": "ML-DSA-65",
            "public_key_fingerprint": ml_dsa_65.fingerprint(self.public_key),
        }
        Draft202012Validator(LAG_REPORT_SCHEMA).validate(payload)
        canonical, sig_hex = sign_canonical(payload, self.secret_key)
        out_dir = self.output_root / report.migration_id / "d5"
        safe_ts = report.timestamp.replace(":", "-")
        json_path = out_dir / f"lag-report-{safe_ts}.json"
        sig_path = out_dir / f"lag-report-{safe_ts}.json.sig"
        _atomic_write(json_path, canonical)
        _atomic_write(sig_path, sig_hex.encode("ascii"))
        return json_path


__all__ = ["LagMonitor", "LagMonitorState"]
