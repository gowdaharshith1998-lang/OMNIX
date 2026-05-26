"""Tests for the MySQL DDL parser (D1 P1)."""

from __future__ import annotations

from omnix.dm._types import ParseFailure, SchemaSpec
from omnix.dm.d1_schema_understanding.ddl_parser import parse


def test_mysql_backtick_table_and_columns(petclinic_mysql_ddl):
    spec = parse(petclinic_mysql_ddl, "mysql")
    assert isinstance(spec, SchemaSpec)
    assert spec.tables[0].name == "owner"
    cols = {c.name: c for c in spec.tables[0].columns}
    assert "id" in cols
    assert cols["id"].dialect_specific.get("auto_increment") is True
    assert cols["id"].primary_key is True
    assert cols["city"].dialect_specific.get("charset") == "utf8mb4"
    assert cols["city"].dialect_specific.get("collate") == "utf8mb4_general_ci"


def test_mysql_decimal_precision_preserved():
    ddl = "CREATE TABLE prices (id INT, amount DECIMAL(10,2) NOT NULL DEFAULT 0);"
    spec = parse(ddl, "mysql")
    assert isinstance(spec, SchemaSpec)
    cols = {c.name: c for c in spec.tables[0].columns}
    assert cols["amount"].raw_type.upper().startswith("DECIMAL")
    assert cols["amount"].normalized_type == "DECIMAL"
    assert cols["amount"].nullable is False


def test_mysql_failure_on_malformed():
    res = parse("CREATE TABLE missing_close (a INT", "mysql")
    assert isinstance(res, (ParseFailure, SchemaSpec))
    if isinstance(res, SchemaSpec):
        assert res.parse_warnings  # honesty: warning surfaced
