"""Cross-cutting D4 + D5 invariants (Hypothesis property tests).

These guard the load-bearing axioms of PR C:

* Row conservation: rows_read == rows_written + rows_quarantined per batch.
* batch_id deterministic from inputs.
* CDC LSN never advances past an unconfirmed event.
* Predecessor hash chain integrity for every emitted receipt.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from omnix.crypto import ml_dsa_65
from omnix.dm._types import (
    BatchReceipt,
    ChangeEvent,
    ColumnMapping,
    ColumnSpec,
    SchemaSpec,
    TableSpec,
)
from omnix.dm.d4_bulk_import._primitives import make_batch_id
from omnix.dm.d4_bulk_import.batch_receipt_emitter import emit as emit_receipt
from omnix.dm.d4_bulk_import.consumer import ConsumedBundle
from omnix.dm.d4_bulk_import.orchestrator import TargetDBInfo, run_bulk_import
from omnix.dm.d5_change_data_capture.cdc_replayer import run_cdc_replay


@pytest.fixture
def keys():
    return ml_dsa_65.keypair(seed=b"\xab" * 48)


@given(
    migration_id=st.from_regex(r"^[a-z][a-z0-9-]{0,20}$", fullmatch=True),
    table=st.from_regex(r"^[a-z_][a-z0-9_]{0,15}$", fullmatch=True),
    batch_no=st.integers(min_value=0, max_value=10_000),
)
@settings(max_examples=50, deadline=None)
def test_batch_id_deterministic(migration_id, table, batch_no):
    a = make_batch_id(migration_id, table, batch_no)
    b = make_batch_id(migration_id, table, batch_no)
    assert a == b
    assert len(a) == 64


def test_row_conservation_across_a_synthetic_migration(tmp_path, keys):
    """For every BatchReceipt that lands on disk: rows_read =
    rows_written + rows_quarantined. Never silently drops."""
    pk, sk = keys

    def _col(name):
        return ColumnSpec(
            name=name,
            raw_type="STRING",
            normalized_type="STRING",
            nullable=True,
            default=None,
            primary_key=name == "id",
            unique=False,
            comment=None,
        )

    bundle = ConsumedBundle(
        migration_id="row-cons",
        column_mappings=(
            ColumnMapping("t", "id", "t", "id", 0.95, "ok"),
            ColumnMapping("t", "name", "t", "name", 0.95, "ok"),
        ),
        findings=(),
        legacy_schema=SchemaSpec(
            dialect="postgres",
            name="s",
            tables=(TableSpec(name="t", columns=(_col("id"), _col("name")), primary_key=("id",)),),
        ),
        target_schema=SchemaSpec(
            dialect="postgres",
            name="s",
            tables=(TableSpec(name="t", columns=(_col("id"), _col("name")), primary_key=("id",)),),
        ),
        transformer_specs={"t.name": {"python_source": "def transform(v):\n    return v\n"}},
        transformer_halts={},
        spec_canonical_hashes={
            "t.name": hashlib.sha256(b"def transform(v):\n    return v\n").hexdigest()
        },
        predecessor_hash=hashlib.sha256(b"d2").hexdigest(),
        unmapped_columns=(),
    )

    class _Cur:
        def __init__(self, rows):
            self._rows = list(rows)
            self.itersize = None

        def execute(self, *a, **k):
            pass

        def fetchmany(self, n):
            chunk, self._rows = self._rows[:n], self._rows[n:]
            return chunk

        def close(self):
            pass

    class _Legacy:
        def cursor(self, *, name=None):
            return _Cur([(i, f"u{i}") for i in range(7)])

    class _Target:
        def cursor(self):
            return _CurT()

        def commit(self):
            pass

    class _CurT:
        def execute(self, *a, **k):
            pass

        def fetchone(self):
            return None

        def copy_expert(self, *a, **k):
            pass

    run_bulk_import(
        bundle=bundle,
        legacy_conn=_Legacy(),
        target_conn=_Target(),
        legacy_dialect="postgres",
        target_dialect="postgres",
        target_db_info=TargetDBInfo("u", "h", 5432, "db"),
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
        use_copy=False,
    )
    for path in (tmp_path / "row-cons" / "d4").glob("batch-receipt-*.json"):
        payload = json.loads(path.read_text())
        assert payload["rows_read"] == payload["rows_written"] + payload["rows_quarantined"]


def test_cdc_lsn_never_advances_past_unconfirmed(tmp_path, keys):
    """If the target write fails, state.last_applied_lsn must remain at the
    previous successful LSN — never silently advance."""
    pk, sk = keys

    class _Target:
        def __init__(self):
            self.calls = 0
            self.committed = []

        def cursor(self):
            return _Cur(self)

        def commit(self):
            self.committed.append(True)

    class _Cur:
        def __init__(self, parent):
            self.parent = parent

        def execute(self, *a, **k):
            self.parent.calls += 1
            if self.parent.calls == 2:
                raise RuntimeError("simulated fail on second event")

    events = [
        ChangeEvent(
            op="I",
            relation_id=1,
            schema_name="public",
            table_name="t",
            lsn="0/100",
            xid=1,
            commit_timestamp="2026",
            before=None,
            after=(("id", 1),),
        ),
        ChangeEvent(
            op="I",
            relation_id=1,
            schema_name="public",
            table_name="t",
            lsn="0/200",  # this one fails
            xid=2,
            commit_timestamp="2026",
            before=None,
            after=(("id", 2),),
        ),
    ]
    state = run_cdc_replay(
        events=events,
        migration_id="cdc-lsn",
        bundle_specs={},
        column_mapping_by_table={"t": {"id": "id"}},
        target_conn=_Target(),
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    # Watermark advanced only to the first (successful) event's LSN.
    assert state.last_applied_lsn == "0/100"
    assert state.events_quarantined == 1


def test_chain_integrity_predecessor_hash_must_be_64_char_hex(tmp_path, keys):
    """The receipt emitter MUST reject malformed predecessor hashes — even if
    every other field is valid, anything that breaks the chain audit fails
    fast."""
    pk, sk = keys
    receipt = BatchReceipt(
        migration_id="m1",
        table="t",
        batch_no=0,
        batch_id=make_batch_id("m1", "t", 0),
        predecessor_hash="not-a-hash",
        rows_read=0,
        rows_written=0,
        rows_quarantined=0,
        quarantine_offsets=(),
        transformer_spec_hashes=(),
        target_db_fingerprint="cc" * 32,
        timestamp_start="2026",
        timestamp_end="2026",
        elapsed_seconds=0.0,
    )
    with pytest.raises(ValueError):
        emit_receipt(receipt, secret_key=sk, public_key=pk, output_root=tmp_path)


@given(num_events=st.integers(min_value=0, max_value=20))
@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_idempotent_replay_skips_repeats(num_events, tmp_path, keys):
    """Re-delivering the same LSN twice MUST land on idempotent_skip, never
    on a second target write."""
    pk, sk = keys

    class _Target:
        def __init__(self):
            self.writes = 0

        def cursor(self):
            return _Cur(self)

        def commit(self):
            pass

    class _Cur:
        def __init__(self, parent):
            self.parent = parent

        def execute(self, *a, **k):
            self.parent.writes += 1

    events = [
        ChangeEvent(
            op="I",
            relation_id=1,
            schema_name="public",
            table_name="t",
            lsn=f"0/{i:X}",
            xid=i,
            commit_timestamp="2026",
            before=None,
            after=(("id", i),),
        )
        for i in range(num_events)
    ]
    # Duplicate every event with the same LSN
    duplicated = []
    for e in events:
        duplicated.append(e)
        duplicated.append(e)
    target = _Target()
    state = run_cdc_replay(
        events=duplicated,
        migration_id=f"idem-{num_events}",
        bundle_specs={},
        column_mapping_by_table={"t": {"id": "id"}},
        target_conn=target,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    assert state.events_replayed == num_events
    assert state.events_idempotent_skipped == num_events
