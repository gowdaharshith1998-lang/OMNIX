"""Row / Batch primitives tests (P2)."""

from __future__ import annotations

import datetime
import decimal

import pytest

from omnix.dm._types import Batch, Row
from omnix.dm.d4_bulk_import._primitives import (
    deserialize_batch,
    make_batch_id,
    normalize_row,
    serialize_batch,
)


def test_batch_id_is_deterministic():
    a = make_batch_id("acme-2026-05-27", "owners", 0)
    b = make_batch_id("acme-2026-05-27", "owners", 0)
    assert a == b
    assert len(a) == 64
    # different inputs → different ids
    assert make_batch_id("acme-2026-05-27", "owners", 1) != a
    assert make_batch_id("acme-2026-05-28", "owners", 0) != a


def test_normalize_row_sorts_columns():
    r = normalize_row("owners", "1", {"zeta": 99, "alpha": 1, "mid": 50})
    assert [c for c, _ in r.column_values] == ["alpha", "mid", "zeta"]


def test_serialize_deserialize_roundtrip():
    rows = (
        normalize_row("owners", "1", {"id": 1, "email": "a@b"}),
        normalize_row("owners", "2", {"id": 2, "email": "c@d"}),
    )
    batch = Batch(
        migration_id="m1",
        table="owners",
        batch_no=0,
        batch_id=make_batch_id("m1", "owners", 0),
        rows=rows,
        snapshot_lsn="0/16B5D68",
    )
    data = serialize_batch(batch)
    back = deserialize_batch(data)
    assert back == batch


def test_datetime_decimal_bytes_roundtrip():
    rows = (
        normalize_row(
            "owners",
            "1",
            {
                "ts": datetime.datetime(2026, 5, 27, 12, 0, tzinfo=datetime.timezone.utc),
                "dt": datetime.date(2026, 5, 27),
                "amt": decimal.Decimal("99.99"),
                "blob": b"\x00\x01\x02",
            },
        ),
    )
    batch = Batch(
        migration_id="m1",
        table="owners",
        batch_no=0,
        batch_id=make_batch_id("m1", "owners", 0),
        rows=rows,
    )
    back = deserialize_batch(serialize_batch(batch))
    cols = dict(back.rows[0].column_values)
    assert isinstance(cols["ts"], datetime.datetime)
    assert cols["ts"].tzinfo is not None
    assert isinstance(cols["dt"], datetime.date)
    assert cols["amt"] == decimal.Decimal("99.99")
    assert cols["blob"] == b"\x00\x01\x02"


def test_empty_rows_batch_serializes():
    batch = Batch(
        migration_id="m1",
        table="owners",
        batch_no=0,
        batch_id=make_batch_id("m1", "owners", 0),
        rows=(),
    )
    back = deserialize_batch(serialize_batch(batch))
    assert back.rows == ()


def test_frozen_batch_rejects_mutation():
    batch = Batch(
        migration_id="m1",
        table="owners",
        batch_no=0,
        batch_id=make_batch_id("m1", "owners", 0),
        rows=(),
    )
    with pytest.raises(Exception):
        batch.rows = ()  # type: ignore[misc]


def test_migration_id_pattern_enforced():
    with pytest.raises(ValueError):
        make_batch_id("ACME!!", "owners", 0)
    with pytest.raises(ValueError):
        make_batch_id("-leading-hyphen", "owners", 0)


def test_large_batch_roundtrip():
    rows = tuple(
        normalize_row("owners", str(i), {"id": i, "email": f"user{i}@example.com"})
        for i in range(10_000)
    )
    batch = Batch(
        migration_id="m1",
        table="owners",
        batch_no=0,
        batch_id=make_batch_id("m1", "owners", 0),
        rows=rows,
    )
    back = deserialize_batch(serialize_batch(batch))
    assert len(back.rows) == 10_000
    assert back.rows[5000].pk_value_repr == "5000"
