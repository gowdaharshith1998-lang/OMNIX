"""FK topological order tests for D4."""

from __future__ import annotations

import pytest

from omnix.dm._types import ColumnSpec, ForeignKeySpec, SchemaSpec, TableSpec
from omnix.dm.d4_bulk_import._fk_topo import (
    CycleInFKGraphError,
    InconsistentReceiptStateError,
    build_fk_topo_order,
)


def _col(name: str = "id") -> ColumnSpec:
    return ColumnSpec(
        name=name,
        raw_type="INTEGER",
        normalized_type="INTEGER",
        nullable=False,
        default=None,
        primary_key=True,
        unique=True,
        comment=None,
    )


def _table(name: str, fks=()) -> TableSpec:
    return TableSpec(
        name=name,
        columns=(_col(),),
        primary_key=("id",),
        foreign_keys=tuple(fks),
        indexes=(),
        comment=None,
    )


def _fk(from_table: str, to_table: str) -> ForeignKeySpec:
    return ForeignKeySpec(
        name=f"fk_{from_table}_{to_table}",
        from_table=from_table,
        from_columns=("id",),
        to_table=to_table,
        to_columns=("id",),
    )


def _schema(*tables) -> SchemaSpec:
    return SchemaSpec(dialect="postgres", name="t", tables=tuple(tables))


def test_linear_dag_order():
    schema = _schema(
        _table("a"),
        _table("b", fks=(_fk("b", "a"),)),
        _table("c", fks=(_fk("c", "b"),)),
    )
    out = build_fk_topo_order(schema)
    assert out.order == ("a", "b", "c")
    assert out.self_referencing == ()


def test_branching_dag_order_is_valid():
    schema = _schema(
        _table("root"),
        _table("left", fks=(_fk("left", "root"),)),
        _table("right", fks=(_fk("right", "root"),)),
    )
    out = build_fk_topo_order(schema)
    assert out.order[0] == "root"
    assert set(out.order[1:]) == {"left", "right"}


def test_cycle_raises_without_deferred():
    schema = _schema(
        _table("a", fks=(_fk("a", "b"),)),
        _table("b", fks=(_fk("b", "a"),)),
    )
    with pytest.raises(CycleInFKGraphError) as exc:
        build_fk_topo_order(schema)
    assert set(exc.value.cycle_tables) == {"a", "b"}


def test_cycle_allowed_with_deferred_flag():
    schema = _schema(
        _table("a", fks=(_fk("a", "b"),)),
        _table("b", fks=(_fk("b", "a"),)),
    )
    out = build_fk_topo_order(schema, allow_deferred_cycles=True)
    assert set(out.deferred_cycle) == {"a", "b"}
    assert set(out.order) == {"a", "b"}


def test_self_reference_surfaced_but_allowed():
    schema = _schema(_table("employees", fks=(_fk("employees", "employees"),)))
    out = build_fk_topo_order(schema)
    assert out.order == ("employees",)
    assert out.self_referencing == ("employees",)


def test_empty_schema_returns_empty_order():
    out = build_fk_topo_order(_schema())
    assert out.order == ()


def test_missing_fk_target_raises():
    schema = _schema(_table("a", fks=(_fk("a", "ghost"),)))
    with pytest.raises(InconsistentReceiptStateError):
        build_fk_topo_order(schema)
