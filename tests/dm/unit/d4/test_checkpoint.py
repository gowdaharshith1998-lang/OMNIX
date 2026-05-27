"""Checkpoint round-trip tests."""

from __future__ import annotations

import json

from omnix.dm.d4_bulk_import.checkpoint import (
    CheckpointState,
    TableCheckpoint,
    read_checkpoint,
    write_checkpoint,
)


def test_roundtrip(tmp_path):
    state = CheckpointState(
        migration_id="m1",
        tables={
            "owners": TableCheckpoint(table="owners", last_batch_no_complete=3, last_pk_seen="3"),
            "pets": TableCheckpoint(table="pets", last_batch_no_complete=0, last_pk_seen=None),
        },
    )
    path = tmp_path / "ckpt.json"
    write_checkpoint(path, state)
    back = read_checkpoint(path)
    assert back == state


def test_read_missing_returns_none(tmp_path):
    assert read_checkpoint(tmp_path / "absent.json") is None


def test_atomic_write_no_tmp_left(tmp_path):
    state = CheckpointState(migration_id="m1", tables={})
    path = tmp_path / "c.json"
    write_checkpoint(path, state)
    tmps = list(tmp_path.glob("*.tmp"))
    assert not tmps
