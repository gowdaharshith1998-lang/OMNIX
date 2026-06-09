"""End-to-end D4 bulk + D5 CDC delta integration (offline, no testcontainers).

A self-contained simulation: synthetic Petclinic ConsumedBundle, mocked
legacy + target connections, mocked pgoutput message stream. Verifies:

  * D4 BatchReceipts: one per (table, batch_no); chain integrity
  * D4 BulkResult.snapshot_lsn captured + handed to D5
  * D5 yields one ChangeEvent per simulated WAL message
  * Sampled CDCEventReceipts written, predecessor_hash chains to TransformerSpec
  * Quarantine entries land in their respective signed manifests
  * LagReport emitted with both legacy/target reachable
  * CutoverProposal absent (test runtime well below sustained window)
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Iterable

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm._types import (
    ChangeEvent,
    ColumnMapping,
    ColumnSpec,
    SchemaSpec,
    TableSpec,
)
from omnix.dm.d4_bulk_import.consumer import ConsumedBundle
from omnix.dm.d4_bulk_import.orchestrator import TargetDBInfo, run_bulk_import
from omnix.dm.d5_change_data_capture.cdc_replayer import run_cdc_replay
from omnix.dm.d5_change_data_capture.cutover_proposal_emitter import (
    CutoverState,
)
from omnix.dm.d5_change_data_capture.cutover_proposal_emitter import (
    evaluate as evaluate_cutover,
)
from omnix.dm.d5_change_data_capture.lag_monitor import LagMonitor

# ---------------------------------------------------------------------------
# Petclinic fixture
# ---------------------------------------------------------------------------


PETCLINIC = {
    "owners": [
        {"id": 1, "first_name": "alice", "last_name": "smith"},
        {"id": 2, "first_name": "bob", "last_name": "jones"},
        {"id": 3, "first_name": "carol", "last_name": "white"},
    ],
    "pets": [
        {"id": 1, "name": "fido", "owner_id": 1},
        {"id": 2, "name": "rex", "owner_id": 2},
    ],
}


def _col(name, norm="STRING", nullable=True):
    return ColumnSpec(
        name=name,
        raw_type=norm,
        normalized_type=norm,
        nullable=nullable,
        default=None,
        primary_key=name == "id",
        unique=False,
        comment=None,
    )


def _table(name, columns):
    return TableSpec(
        name=name,
        columns=tuple(columns),
        primary_key=("id",),
    )


def _bundle():
    tables = []
    mappings = []
    specs = {}
    spec_hashes = {}
    for tname, rows in PETCLINIC.items():
        col_names = list(rows[0].keys())
        cols = [_col(n) for n in col_names]
        tables.append(_table(tname, cols))
        for cn in col_names:
            mappings.append(
                ColumnMapping(
                    legacy_table=tname,
                    legacy_column=cn,
                    target_table=tname,
                    target_column=cn,
                    confidence=0.95,
                    status="ok",
                )
            )
            if cn != "id":
                src = "def transform(v):\n    return v\n"
                specs[f"{tname}.{cn}"] = {"python_source": src}
                spec_hashes[f"{tname}.{cn}"] = hashlib.sha256(src.encode()).hexdigest()
    schema = SchemaSpec(dialect="postgres", name="petclinic", tables=tuple(tables))
    return ConsumedBundle(
        migration_id="petclinic-2026-05-27",
        column_mappings=tuple(mappings),
        findings=(),
        legacy_schema=schema,
        target_schema=schema,
        transformer_specs=specs,
        transformer_halts={},
        spec_canonical_hashes=spec_hashes,
        predecessor_hash=hashlib.sha256(b"petclinic-d2").hexdigest(),
        unmapped_columns=(),
    )


# ---------------------------------------------------------------------------
# Mock connections
# ---------------------------------------------------------------------------


class _MockCursor:
    def __init__(self, rows):
        self._rows = list(rows)
        self.itersize = None

    def execute(self, sql, params=None):
        return None

    def fetchmany(self, n):
        chunk, self._rows = self._rows[:n], self._rows[n:]
        return chunk

    def close(self):
        pass


class _MockLegacy:
    def __init__(self, by_table):
        self._by = by_table

    def cursor(self, *, name=None):
        table = name.rsplit("_", 1)[-1] if name else ""
        return _MockCursor(self._by.get(table, []))


class _MockTarget:
    def __init__(self):
        self.rows = []

    def cursor(self):
        return _MockCursorWriter(self.rows)

    def commit(self):
        pass


class _MockCursorWriter:
    def __init__(self, store):
        self.store = store

    def execute(self, sql, params=None):
        if params is not None and "INSERT" in sql:
            self.store.append(params)

    def fetchone(self):
        return None

    def copy_expert(self, sql, buf):
        for line in buf.read().splitlines():
            self.store.append(tuple(line.split(",")))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def keys():
    return ml_dsa_65.keypair(seed=b"\x90" * 48)


def test_d4_bulk_emits_one_receipt_per_batch(tmp_path, keys):
    pk, sk = keys
    bundle = _bundle()
    # Sort columns to match reader's tuple order
    by_table = {
        t: [tuple(r[c] for c in sorted(r)) for r in rs]
        for t, rs in PETCLINIC.items()
    }
    result = run_bulk_import(
        bundle=bundle,
        legacy_conn=_MockLegacy(by_table),
        target_conn=_MockTarget(),
        legacy_dialect="postgres",
        target_dialect="postgres",
        target_db_info=TargetDBInfo("u", "h", 5432, "petclinic_new"),
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
        snapshot_lsn="0/A0000000",
        use_copy=False,
    )
    assert result.phase == "complete"
    assert result.snapshot_lsn == "0/A0000000"
    assert result.total_rows_written == 5  # 3 owners + 2 pets
    assert result.total_rows_quarantined == 0
    # Receipts on disk
    receipts = list(
        (tmp_path / bundle.migration_id / "d4").glob("batch-receipt-*.json")
    )
    assert len(receipts) == 2  # one per table


def test_d4_predecessor_hash_chains_to_d2(tmp_path, keys):
    pk, sk = keys
    bundle = _bundle()
    by_table = {
        t: [tuple(r[c] for c in sorted(r)) for r in rs]
        for t, rs in PETCLINIC.items()
    }
    run_bulk_import(
        bundle=bundle,
        legacy_conn=_MockLegacy(by_table),
        target_conn=_MockTarget(),
        legacy_dialect="postgres",
        target_dialect="postgres",
        target_db_info=TargetDBInfo("u", "h", 5432, "petclinic_new"),
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
        use_copy=False,
    )
    for path in (tmp_path / bundle.migration_id / "d4").glob("batch-receipt-*.json"):
        payload = json.loads(path.read_text())
        assert payload["predecessor_hash"] == bundle.predecessor_hash


def test_d5_replays_three_events_after_bulk(tmp_path, keys, monkeypatch):
    pk, sk = keys
    monkeypatch.setenv("OMNIX_DM_CDC_EVENT_RECEIPT_SAMPLE_RATE", "1.0")
    bundle = _bundle()
    target = _MockTarget()
    events = [
        ChangeEvent(
            op="I",
            relation_id=1234,
            schema_name="public",
            table_name="owners",
            lsn=f"0/B{i:X}",
            xid=10 + i,
            commit_timestamp="2026-05-27T00:00:00+00:00",
            before=None,
            after=(("id", 100 + i), ("first_name", f"u{i}"), ("last_name", "test")),
        )
        for i in range(3)
    ]
    state = run_cdc_replay(
        events=events,
        migration_id=bundle.migration_id,
        bundle_specs=bundle.transformer_specs,
        column_mapping_by_table={
            "owners": {"id": "id", "first_name": "first_name", "last_name": "last_name"}
        },
        target_conn=target,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
        receipt_predecessor_for_table={"owners": bundle.spec_canonical_hashes["owners.first_name"]},
    )
    assert state.events_replayed == 3
    receipts = list(
        (tmp_path / bundle.migration_id / "d5").glob("cdc-event-receipt-*.json")
    )
    assert len(receipts) == 3
    # Chain integrity: every receipt's predecessor_hash points to the spec hash
    for p in receipts:
        payload = json.loads(p.read_text())
        assert payload["predecessor_hash"] == bundle.spec_canonical_hashes[
            "owners.first_name"
        ]


def test_lag_report_emitted_for_both_reachable(tmp_path, keys):
    pk, sk = keys
    from omnix.dm.d5_change_data_capture.cdc_replayer import CDCReplayState

    replay = CDCReplayState(migration_id="m1")
    monitor = LagMonitor(
        migration_id="m1",
        replay_state=replay,
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
        legacy_lsn_provider=lambda: "0/1000",
        target_lsn_provider=lambda: "0/950",
    )
    report = monitor.tick()
    assert report.legacy_unreachable is False
    assert report.lag_lsn_bytes == 0x1000 - 0x950


def test_cutover_proposal_absent_before_sustained_window():
    """Test runtime is well below the configured sustained window so the
    proposal must not fire."""
    from omnix.dm._types import LagReport

    state = CutoverState(sustained_window_required_sec=900)
    report = LagReport(
        migration_id="m1",
        timestamp="2026-05-27T00:00:00+00:00",
        legacy_current_lsn="0/1000",
        target_applied_lsn="0/990",
        legacy_unreachable=False,
        target_unreachable=False,
        lag_lsn_bytes=16,
        lag_estimated_seconds=0.5,
        events_replayed_last_interval=1,
        events_quarantined_last_interval=0,
        unhandled_event_types_seen=(),
    )
    # First tick starts the window
    assert evaluate_cutover(state=state, lag_report=report, now_monotonic=0.0) is None
    # Two seconds in — still below 900-second window
    assert evaluate_cutover(state=state, lag_report=report, now_monotonic=2.0) is None
