"""Executor pool tests (P4)."""

from __future__ import annotations

import pytest

from omnix.dm._types import Batch
from omnix.dm.d4_bulk_import._primitives import make_batch_id, normalize_row
from omnix.dm.d4_bulk_import.executor_pool import ExecutorPool

_PASSTHROUGH = {"python_source": "def transform(v):\n    return v\n"}
_UPPER = {"python_source": "def transform(v):\n    return v.upper() if v is not None else None\n"}
_BAD_TYPE = {"python_source": "def transform(v):\n    return v.strip()\n"}  # fails on int
_ESCAPE = {
    "python_source": 'def transform(v):\n    return __import__("os").system("id")\n'
}


def _batch(rows_dict):
    rows = tuple(
        normalize_row("owners", repr(i), row) for i, row in enumerate(rows_dict)
    )
    return Batch(
        migration_id="m1",
        table="owners",
        batch_no=0,
        batch_id=make_batch_id("m1", "owners", 0),
        rows=rows,
    )


def test_happy_path_single_column():
    batch = _batch([{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}])
    with ExecutorPool(worker_count=2) as pool:
        out, quar = pool.submit(
            batch,
            transformer_specs={"name": _UPPER},
            column_mapping={"id": "id", "name": "name"},
        )
    assert quar == []
    assert len(out.transformed_rows) == 2
    cols = dict(out.transformed_rows[0].target_column_values)
    assert cols["name"] == "ALICE"
    assert cols["id"] == 1  # passed through


def test_security_violation_quarantines_row():
    batch = _batch([{"name": "x"}])
    with ExecutorPool(worker_count=1) as pool:
        out, quar = pool.submit(
            batch,
            transformer_specs={"name": _ESCAPE},
            column_mapping={"name": "name"},
        )
    assert len(out.transformed_rows) == 0
    assert len(quar) == 1
    assert quar[0].failure_category == "security_violation"


def test_transform_error_quarantines_row():
    batch = _batch([{"id": 7}])  # int — .strip() will fail
    with ExecutorPool(worker_count=1) as pool:
        out, quar = pool.submit(
            batch,
            transformer_specs={"id": _BAD_TYPE},
            column_mapping={"id": "id"},
        )
    assert len(out.transformed_rows) == 0
    assert len(quar) == 1
    assert quar[0].failure_category == "transform_error"


def test_partial_failure_only_offending_rows_quarantined():
    batch = _batch(
        [
            {"name": "good"},
            {"name": 42},   # int — strip() fails
            {"name": "fine"},
        ]
    )
    with ExecutorPool(worker_count=2) as pool:
        out, quar = pool.submit(
            batch,
            transformer_specs={"name": _BAD_TYPE},
            column_mapping={"name": "name"},
        )
    assert len(out.transformed_rows) == 2
    assert len(quar) == 1
    assert quar[0].row_offset == 1


def test_no_transformers_passes_rows_through():
    batch = _batch([{"id": 1, "email": "a@b"}])
    with ExecutorPool(worker_count=1) as pool:
        out, quar = pool.submit(
            batch,
            transformer_specs={},
            column_mapping={"id": "id", "email": "email"},
        )
    assert quar == []
    assert len(out.transformed_rows) == 1
    cols = dict(out.transformed_rows[0].target_column_values)
    assert cols == {"id": 1, "email": "a@b"}


def test_pool_close_idempotent():
    pool = ExecutorPool(worker_count=1)
    pool.close()
    pool.close()  # second close is no-op
    with pytest.raises(RuntimeError):
        pool.submit(
            _batch([{"id": 1}]),
            transformer_specs={},
            column_mapping={"id": "id"},
        )


def test_column_mapping_renames_target_columns():
    batch = _batch([{"first_name": "alice"}])
    with ExecutorPool(worker_count=1) as pool:
        out, _ = pool.submit(
            batch,
            transformer_specs={"first_name": _PASSTHROUGH},
            column_mapping={"first_name": "given_name"},
        )
    cols = dict(out.transformed_rows[0].target_column_values)
    assert cols == {"given_name": "alice"}


def test_quarantine_entry_carries_pk_hash_not_pk_value():
    batch = _batch([{"name": 99}])
    with ExecutorPool(worker_count=1) as pool:
        _, quar = pool.submit(
            batch,
            transformer_specs={"name": _BAD_TYPE},
            column_mapping={"name": "name"},
        )
    assert len(quar[0].legacy_pk_value_hash) == 64
    # raw pk value (the int 99) must NOT appear in the hash
    assert "99" not in quar[0].legacy_pk_value_hash
