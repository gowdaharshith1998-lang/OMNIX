"""BatchReceipt emitter tests (P6)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm._types import BatchReceipt
from omnix.dm.d4_bulk_import._primitives import make_batch_id
from omnix.dm.d4_bulk_import.batch_receipt_emitter import (
    db_fingerprint,
    emit,
)
from omnix.dm.receipts.ml_dsa_65_signer import verify_canonical


@pytest.fixture
def keys():
    return ml_dsa_65.keypair(seed=b"\xbb" * 48)


def _receipt(table="owners", batch_no=0) -> BatchReceipt:
    return BatchReceipt(
        migration_id="m1",
        table=table,
        batch_no=batch_no,
        batch_id=make_batch_id("m1", table, batch_no),
        predecessor_hash=hashlib.sha256(b"d2").hexdigest(),
        rows_read=10,
        rows_written=9,
        rows_quarantined=1,
        quarantine_offsets=(3,),
        transformer_spec_hashes=("ab" * 32,),
        target_db_fingerprint=db_fingerprint("writer", "target.db", 5432, "acme_new"),
        timestamp_start="2026-05-27T00:00:00+00:00",
        timestamp_end="2026-05-27T00:00:01+00:00",
        elapsed_seconds=1.234,
    )


def test_happy_emit_writes_json_and_sig(keys, tmp_path):
    pk, sk = keys
    path = emit(_receipt(), secret_key=sk, public_key=pk, output_root=tmp_path)
    assert path.exists()
    sig = (path.parent / (path.name + ".sig")).read_text()
    payload = json.loads(path.read_text())
    assert verify_canonical(payload, sig, pk)


def test_predecessor_hash_validated_pre_sign(keys, tmp_path):
    pk, sk = keys
    bad = BatchReceipt(
        migration_id="m1",
        table="owners",
        batch_no=0,
        batch_id=make_batch_id("m1", "owners", 0),
        predecessor_hash="not-hex",
        rows_read=1,
        rows_written=1,
        rows_quarantined=0,
        quarantine_offsets=(),
        transformer_spec_hashes=(),
        target_db_fingerprint="dd" * 32,
        timestamp_start="2026",
        timestamp_end="2026",
        elapsed_seconds=0.0,
    )
    with pytest.raises(ValueError):
        emit(bad, secret_key=sk, public_key=pk, output_root=tmp_path)


def test_batch_id_validated_pre_sign(keys, tmp_path):
    pk, sk = keys
    bad = BatchReceipt(
        migration_id="m1",
        table="owners",
        batch_no=0,
        batch_id="not-hex",
        predecessor_hash=hashlib.sha256(b"x").hexdigest(),
        rows_read=1,
        rows_written=1,
        rows_quarantined=0,
        quarantine_offsets=(),
        transformer_spec_hashes=(),
        target_db_fingerprint="dd" * 32,
        timestamp_start="x",
        timestamp_end="x",
        elapsed_seconds=0.0,
    )
    with pytest.raises(ValueError):
        emit(bad, secret_key=sk, public_key=pk, output_root=tmp_path)


def test_db_fingerprint_does_not_contain_password():
    fp = db_fingerprint("writer", "target.db", 5432, "acme")
    assert "password" not in fp
    assert "secret" not in fp
    assert len(fp) == 64


def test_db_fingerprint_deterministic():
    a = db_fingerprint("writer", "h", 5432, "d")
    b = db_fingerprint("writer", "h", 5432, "d")
    assert a == b
    assert db_fingerprint("writer", "h", 5433, "d") != a


def test_chain_integrity_predecessor_hash_persisted(keys, tmp_path):
    pk, sk = keys
    pred = hashlib.sha256(b"d2-manifest").hexdigest()
    receipt = BatchReceipt(
        migration_id="m1",
        table="owners",
        batch_no=0,
        batch_id=make_batch_id("m1", "owners", 0),
        predecessor_hash=pred,
        rows_read=0,
        rows_written=0,
        rows_quarantined=0,
        quarantine_offsets=(),
        transformer_spec_hashes=(),
        target_db_fingerprint="dd" * 32,
        timestamp_start="x",
        timestamp_end="x",
        elapsed_seconds=0.0,
    )
    path = emit(receipt, secret_key=sk, public_key=pk, output_root=tmp_path)
    payload = json.loads(path.read_text())
    assert payload["predecessor_hash"] == pred


def test_atomic_write_no_tmp_left_over(keys, tmp_path):
    pk, sk = keys
    emit(_receipt(), secret_key=sk, public_key=pk, output_root=tmp_path)
    tmps = list((tmp_path / "m1" / "d4").glob("*.tmp"))
    assert not tmps


def test_path_layout(keys, tmp_path):
    pk, sk = keys
    path = emit(_receipt(table="owners", batch_no=3), secret_key=sk, public_key=pk, output_root=tmp_path)
    expected_relative = Path("m1") / "d4" / "batch-receipt-owners-3.json"
    assert str(path).endswith(str(expected_relative))
