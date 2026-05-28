"""CDC replayer tests (P10)."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm._types import ChangeEvent
from omnix.dm.d5_change_data_capture.cdc_replayer import (
    CDCReplayState,
    replay_one,
    run_cdc_replay,
)


@pytest.fixture
def keys():
    return ml_dsa_65.keypair(seed=b"\xee" * 48)


_PASSTHROUGH = {"python_source": "def transform(v):\n    return v\n"}
_UPPER = {"python_source": "def transform(v):\n    return v.upper() if v is not None else None\n"}
_BAD = {
    "python_source": 'def transform(v):\n    return __import__("os").system("id")\n'
}


class _FakeCursor:
    def __init__(self, store):
        self.store = store
        self.fail_next = False

    def execute(self, sql, params=None):
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("simulated target error")
        self.store.append((sql, params))


class _FakeTarget:
    def __init__(self):
        self.applied = []
        self._cursor = _FakeCursor(self.applied)
        self.committed = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed += 1


def _ev(op, lsn, after=None, before=None, table="owners"):
    return ChangeEvent(
        op=op,
        relation_id=1234,
        schema_name="public",
        table_name=table,
        lsn=lsn,
        xid=1,
        commit_timestamp="2026-05-27T00:00:00+00:00",
        before=before,
        after=after,
    )


def test_insert_event_applied(tmp_path, keys):
    pk, sk = keys
    target = _FakeTarget()
    state = run_cdc_replay(
        events=[_ev("I", "0/100", after=(("id", 1), ("name", "alice")))],
        migration_id="m1",
        bundle_specs={"owners.name": _UPPER},
        column_mapping_by_table={"owners": {"id": "id", "name": "name"}},
        target_conn=target,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    assert state.events_replayed == 1
    assert state.events_quarantined == 0
    # Target write occurred
    assert len(target.applied) == 1


def test_update_with_before_tuple_replays(tmp_path, keys):
    pk, sk = keys
    target = _FakeTarget()
    state = run_cdc_replay(
        events=[
            _ev(
                "U",
                "0/200",
                before=(("id", 1), ("name", "old")),
                after=(("id", 1), ("name", "new")),
            )
        ],
        migration_id="m1",
        bundle_specs={"owners.name": _UPPER},
        column_mapping_by_table={"owners": {"id": "id", "name": "name"}},
        target_conn=target,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    assert state.events_replayed == 1


def test_delete_event_applied_from_before_tuple(tmp_path, keys):
    pk, sk = keys
    target = _FakeTarget()
    state = run_cdc_replay(
        events=[_ev("D", "0/300", before=(("id", 1),))],
        migration_id="m1",
        bundle_specs={},
        column_mapping_by_table={"owners": {"id": "id"}},
        target_conn=target,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    assert state.events_replayed == 1


def test_truncate_event_quarantined(tmp_path, keys):
    pk, sk = keys
    target = _FakeTarget()
    state = run_cdc_replay(
        events=[_ev("T", "0/400")],
        migration_id="m1",
        bundle_specs={},
        column_mapping_by_table={"owners": {}},
        target_conn=target,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    assert state.events_quarantined == 1
    assert "Truncate" in state.unhandled_event_types


def test_unknown_relation_quarantined(tmp_path, keys):
    pk, sk = keys
    target = _FakeTarget()
    state = run_cdc_replay(
        events=[_ev("I", "0/500", after=(("id", 1),), table="ghost")],
        migration_id="m1",
        bundle_specs={},
        column_mapping_by_table={"owners": {"id": "id"}},
        target_conn=target,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    assert state.events_quarantined == 1
    assert state.events_replayed == 0


def test_re_delivery_idempotent_skip(tmp_path, keys):
    pk, sk = keys
    target = _FakeTarget()
    state = run_cdc_replay(
        events=[
            _ev("I", "0/100", after=(("id", 1),)),
            _ev("I", "0/100", after=(("id", 1),)),  # same LSN — re-delivery
        ],
        migration_id="m1",
        bundle_specs={},
        column_mapping_by_table={"owners": {"id": "id"}},
        target_conn=target,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    assert state.events_replayed == 1
    assert state.events_idempotent_skipped == 1


def test_security_violation_in_transformer_quarantines(tmp_path, keys):
    pk, sk = keys
    target = _FakeTarget()
    state = run_cdc_replay(
        events=[_ev("I", "0/100", after=(("id", 1), ("name", "x")))],
        migration_id="m1",
        bundle_specs={"owners.name": _BAD},
        column_mapping_by_table={"owners": {"id": "id", "name": "name"}},
        target_conn=target,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    assert state.events_quarantined == 1
    assert state.events_replayed == 0


def test_sample_rate_zero_emits_no_receipts(tmp_path, keys, monkeypatch):
    pk, sk = keys
    target = _FakeTarget()
    monkeypatch.setenv("OMNIX_DM_CDC_EVENT_RECEIPT_SAMPLE_RATE", "0.0")
    state = run_cdc_replay(
        events=[_ev("I", f"0/{i:X}", after=(("id", i),)) for i in range(1, 50)],
        migration_id="m1",
        bundle_specs={},
        column_mapping_by_table={"owners": {"id": "id"}},
        target_conn=target,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    assert state.receipts_emitted == 0


def test_sample_rate_one_emits_every_receipt(tmp_path, keys, monkeypatch):
    pk, sk = keys
    target = _FakeTarget()
    monkeypatch.setenv("OMNIX_DM_CDC_EVENT_RECEIPT_SAMPLE_RATE", "1.0")
    state = run_cdc_replay(
        events=[_ev("I", f"0/{i:X}", after=(("id", i),)) for i in range(1, 6)],
        migration_id="m1",
        bundle_specs={},
        column_mapping_by_table={"owners": {"id": "id"}},
        target_conn=target,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    assert state.receipts_emitted == 5
    # Receipts on disk
    receipts = list((tmp_path / "m1" / "d5").glob("cdc-event-receipt-*.json"))
    assert len(receipts) == 5


def test_predecessor_hash_in_receipt_matches_spec_hash(tmp_path, keys, monkeypatch):
    pk, sk = keys
    target = _FakeTarget()
    monkeypatch.setenv("OMNIX_DM_CDC_EVENT_RECEIPT_SAMPLE_RATE", "1.0")
    spec_hash = hashlib.sha256(b"d3-spec").hexdigest()
    state = run_cdc_replay(
        events=[_ev("I", "0/100", after=(("id", 1),))],
        migration_id="m1",
        bundle_specs={},
        column_mapping_by_table={"owners": {"id": "id"}},
        target_conn=target,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
        receipt_predecessor_for_table={"owners": spec_hash},
    )
    receipt = next((tmp_path / "m1" / "d5").glob("cdc-event-receipt-*.json"))
    payload = json.loads(receipt.read_text())
    assert payload["predecessor_hash"] == spec_hash


def test_target_failure_quarantines_without_advancing_watermark(tmp_path, keys):
    """If target write fails, the LSN watermark MUST NOT advance — otherwise
    a retry would skip the event silently (data loss)."""
    pk, sk = keys
    target = _FakeTarget()
    target._cursor.fail_next = True
    state = run_cdc_replay(
        events=[_ev("I", "0/500", after=(("id", 1),))],
        migration_id="m1",
        bundle_specs={},
        column_mapping_by_table={"owners": {"id": "id"}},
        target_conn=target,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    assert state.events_quarantined == 1
    assert state.last_applied_lsn is None


def test_event_missing_both_tuples_quarantined(tmp_path, keys):
    pk, sk = keys
    target = _FakeTarget()
    state = run_cdc_replay(
        events=[_ev("U", "0/600")],
        migration_id="m1",
        bundle_specs={},
        column_mapping_by_table={"owners": {"id": "id"}},
        target_conn=target,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    assert state.events_quarantined == 1
