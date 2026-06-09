"""Quarantine log tests (P6)."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm._types import RowQuarantineEntry
from omnix.dm.d4_bulk_import.quarantine import QuarantineLog
from omnix.dm.receipts.ml_dsa_65_signer import verify_canonical


@pytest.fixture
def keys():
    return ml_dsa_65.keypair(seed=b"\xaa" * 48)


def _entry(offset: int = 0, category: str = "transform_error") -> RowQuarantineEntry:
    return RowQuarantineEntry(
        migration_id="m1",
        batch_id="ab" * 32,
        row_offset=offset,
        legacy_table="owners",
        legacy_pk_value_hash="cd" * 32,
        failure_category=category,
        failure_detail="boom",
        transformer_spec_hash=None,
        retry_count=0,
        timestamp="2026-05-27T00:00:00+00:00",
    )


def test_record_appends(keys, tmp_path):
    pk, sk = keys
    log = QuarantineLog(
        migration_id="m1",
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
    )
    log.record(_entry(0))
    log.record(_entry(1))
    assert len(log) == 2


def test_flush_writes_signed_manifest(keys, tmp_path):
    pk, sk = keys
    log = QuarantineLog(
        migration_id="m1",
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
    )
    log.record(_entry())
    path = log.flush()
    assert path is not None
    sig = (path.parent / (path.name + ".sig")).read_text()
    payload = json.loads(path.read_text())
    assert verify_canonical(payload, sig, pk)


def test_file_mode_0600(keys, tmp_path):
    if os.name == "nt":
        pytest.skip("Windows stat mode bits do not preserve POSIX 0600 semantics")
    pk, sk = keys
    log = QuarantineLog(
        migration_id="m1",
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
    )
    log.record(_entry())
    path = log.flush()
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600


def test_values_omitted_by_default(keys, tmp_path):
    pk, sk = keys
    log = QuarantineLog(
        migration_id="m1",
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
    )
    e = RowQuarantineEntry(
        migration_id="m1",
        batch_id="ab" * 32,
        row_offset=0,
        legacy_table="owners",
        legacy_pk_value_hash="cd" * 32,
        failure_category="transform_error",
        failure_detail="boom",
        transformer_spec_hash=None,
        retry_count=0,
        timestamp="2026-05-27T00:00:00+00:00",
        raw_values_json='{"email":"alice@example.com"}',
    )
    log.record(e)
    path = log.flush()
    payload = json.loads(path.read_text())
    assert "raw_values_json" not in payload["entries"][0]


def test_values_included_with_opt_in(keys, tmp_path, monkeypatch):
    pk, sk = keys
    monkeypatch.setenv("OMNIX_DM_QUARANTINE_INCLUDE_VALUES", "1")
    log = QuarantineLog(
        migration_id="m1",
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
    )
    e = RowQuarantineEntry(
        migration_id="m1",
        batch_id="ab" * 32,
        row_offset=0,
        legacy_table="owners",
        legacy_pk_value_hash="cd" * 32,
        failure_category="transform_error",
        failure_detail="boom",
        transformer_spec_hash=None,
        retry_count=0,
        timestamp="2026-05-27T00:00:00+00:00",
        raw_values_json='{"email":"alice@example.com"}',
    )
    log.record(e)
    path = log.flush()
    payload = json.loads(path.read_text())
    assert payload["entries"][0]["raw_values_json"] == '{"email":"alice@example.com"}'


def test_flush_no_op_when_empty(keys, tmp_path):
    pk, sk = keys
    log = QuarantineLog(
        migration_id="m1",
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
    )
    assert log.flush() is None


def test_large_manifest_streams_without_oom(keys, tmp_path):
    pk, sk = keys
    log = QuarantineLog(
        migration_id="m1",
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
    )
    for i in range(1_000):
        log.record(_entry(i))
    path = log.flush()
    payload = json.loads(path.read_text())
    assert len(payload["entries"]) == 1_000


def test_entries_are_reproducible(keys, tmp_path):
    pk, sk = keys
    log1 = QuarantineLog(
        migration_id="m1",
        output_root=tmp_path / "a",
        secret_key=sk,
        public_key=pk,
    )
    log2 = QuarantineLog(
        migration_id="m1",
        output_root=tmp_path / "b",
        secret_key=sk,
        public_key=pk,
    )
    for log in (log1, log2):
        log.record(_entry())
    p1 = log1.flush()
    p2 = log2.flush()
    pl1 = json.loads(p1.read_text())
    pl2 = json.loads(p2.read_text())
    # Only the deterministic content (entries) is compared — signatures vary
    # because the canonical SHA-256 we hash includes the same content but
    # ML-DSA signatures are randomized.
    assert pl1["entries"] == pl2["entries"]
