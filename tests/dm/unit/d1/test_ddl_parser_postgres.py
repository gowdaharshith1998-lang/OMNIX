"""Tests for the PostgreSQL DDL parser (D1 P1)."""

from __future__ import annotations

from omnix.dm._types import ParseFailure, SchemaSpec
from omnix.dm.d1_schema_understanding.ddl_parser import parse


def test_petclinic_pg_happy_path(petclinic_pg_ddl):
    spec = parse(petclinic_pg_ddl, "postgres")
    assert isinstance(spec, SchemaSpec)
    assert {t.name for t in spec.tables} == {"owner", "pet", "visit"}
    owner = next(t for t in spec.tables if t.name == "owner")
    assert owner.primary_key == ("id",)
    cols = {c.name: c for c in owner.columns}
    assert cols["email"].normalized_type == "STRING"
    assert cols["email"].comment == "unique email address"
    assert cols["first_name"].nullable is False
    assert cols["created_at"].normalized_type == "TIMESTAMP_TZ"


def test_postgres_foreign_key_and_index_captured(petclinic_pg_ddl):
    spec = parse(petclinic_pg_ddl, "postgres")
    pet = next(t for t in spec.tables if t.name == "pet")
    assert len(pet.foreign_keys) == 1
    fk = pet.foreign_keys[0]
    assert fk.from_columns == ("owner_id",)
    assert fk.to_table == "owner"
    assert fk.to_columns == ("id",)
    assert fk.on_delete == "CASCADE"
    assert any(i.name == "idx_pet_owner" for i in pet.indexes)


def test_postgres_quoted_identifiers():
    ddl = '''CREATE TABLE "User" ("First Name" VARCHAR(50) NOT NULL, "age" INTEGER);'''
    spec = parse(ddl, "postgres")
    assert isinstance(spec, SchemaSpec)
    table = spec.tables[0]
    assert table.name == "User"
    assert {c.name for c in table.columns} == {"First Name", "age"}


def test_postgres_empty_ddl_returns_failure():
    res = parse("", "postgres")
    assert isinstance(res, ParseFailure)
    assert "empty" in res.reason.lower()


def test_postgres_garbage_returns_failure():
    res = parse("this is not sql at all", "postgres")
    assert isinstance(res, ParseFailure)
    # Codex honesty: we surface the gap rather than returning an empty SchemaSpec
    assert "CREATE TABLE" in res.reason or "no" in res.reason.lower()


def test_postgres_unbalanced_parens_does_not_crash():
    res = parse("CREATE TABLE foo (a INT, b VARCHAR(", "postgres")
    # Either ParseFailure or a SchemaSpec with parse_warnings — never a crash.
    if isinstance(res, SchemaSpec):
        assert res.parse_warnings  # warnings surfaced
    else:
        assert isinstance(res, ParseFailure)
