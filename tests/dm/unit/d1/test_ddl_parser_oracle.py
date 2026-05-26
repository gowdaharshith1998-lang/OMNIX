"""Tests for the Oracle DDL parser (D1 P1)."""

from __future__ import annotations

from omnix.dm._types import ParseFailure, SchemaSpec
from omnix.dm.d1_schema_understanding.ddl_parser import parse


def test_oracle_petclinic_happy_path(petclinic_oracle_ddl):
    spec = parse(petclinic_oracle_ddl, "oracle")
    assert isinstance(spec, SchemaSpec)
    assert {t.name for t in spec.tables} == {"owners", "pets"}
    owners = next(t for t in spec.tables if t.name == "owners")
    cols = {c.name: c for c in owners.columns}
    # Oracle DATE includes time component — flagged for D3
    assert cols["created_at"].dialect_specific.get("flag_for_d3") is True
    assert cols["created_at"].dialect_specific.get("oracle_date_includes_time") is True
    # SEQUENCE detected and warned
    assert any("SEQUENCE" in w for w in spec.parse_warnings)


def test_oracle_number_precision_scale():
    ddl = """CREATE TABLE foo (
        amount NUMBER(38, 10),
        n_only NUMBER(15),
        any_n NUMBER
    );"""
    spec = parse(ddl, "oracle")
    assert isinstance(spec, SchemaSpec)
    cols = {c.name: c for c in spec.tables[0].columns}
    assert cols["amount"].dialect_specific == {"precision": 38, "scale": 10}
    assert cols["n_only"].dialect_specific == {"precision": 15}
    assert cols["any_n"].normalized_type == "DECIMAL"


def test_oracle_timestamp_with_time_zone():
    ddl = "CREATE TABLE foo (a TIMESTAMP WITH TIME ZONE);"
    spec = parse(ddl, "oracle")
    assert isinstance(spec, SchemaSpec)
    assert spec.tables[0].columns[0].normalized_type == "TIMESTAMP_TZ"


def test_oracle_failure_on_garbage():
    res = parse("BEGIN END;", "oracle")
    assert isinstance(res, ParseFailure)
