"""CDC quarantine log tests."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm._types import CDCEventQuarantineEntry
from omnix.dm.d5_change_data_capture.cdc_quarantine import CDCQuarantineLog


@pytest.fixture
def keys():
    return ml_dsa_65.keypair(seed=b"\xdd" * 48)


def _entry() -> CDCEventQuarantineEntry:
    return CDCEventQuarantineEntry(
        migration_id="m1",
        event_lsn="0/16B5D68",
        relation_id=1234,
        table="owners",
        op="I",
        failure_category="transform_error",
        failure_detail="boom",
        timestamp="2026-05-27T00:00:00+00:00",
    )


def test_record_and_flush_signed(tmp_path, keys):
    pk, sk = keys
    log = CDCQuarantineLog(
        migration_id="m1", output_root=tmp_path, secret_key=sk, public_key=pk
    )
    log.record(_entry())
    path = log.flush()
    assert path is not None
    payload = json.loads(path.read_text())
    assert payload["phase"] == "d5_cdc"
    assert len(payload["entries"]) == 1


def test_file_mode_0600(tmp_path, keys):
    if os.name == "nt":
        pytest.skip("Windows stat mode bits do not preserve POSIX 0600 semantics")
    pk, sk = keys
    log = CDCQuarantineLog(
        migration_id="m1", output_root=tmp_path, secret_key=sk, public_key=pk
    )
    log.record(_entry())
    path = log.flush()
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600


def test_empty_flush_is_noop(tmp_path, keys):
    pk, sk = keys
    log = CDCQuarantineLog(
        migration_id="m1", output_root=tmp_path, secret_key=sk, public_key=pk
    )
    assert log.flush() is None


def test_signature_verifies(tmp_path, keys):
    pk, sk = keys
    log = CDCQuarantineLog(
        migration_id="m1", output_root=tmp_path, secret_key=sk, public_key=pk
    )
    log.record(_entry())
    path = log.flush()
    from omnix.dm.receipts.ml_dsa_65_signer import verify_canonical

    sig = (path.parent / (path.name + ".sig")).read_text()
    payload = json.loads(path.read_text())
    assert verify_canonical(payload, sig, pk)
