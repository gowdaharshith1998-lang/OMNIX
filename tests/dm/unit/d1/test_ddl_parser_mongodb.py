"""Tests for the MongoDB schema parser (D1 P1)."""

from __future__ import annotations

from omnix.dm._types import ParseFailure, SchemaSpec
from omnix.dm.d1_schema_understanding.ddl_parser import parse


def test_mongo_petclinic_happy_path(petclinic_mongo_schema):
    spec = parse(petclinic_mongo_schema, "mongodb")
    assert isinstance(spec, SchemaSpec)
    assert {t.name for t in spec.tables} == {"owner", "visit"}
    owner = next(t for t in spec.tables if t.name == "owner")
    names = {c.name for c in owner.columns}
    assert "address.city" in names  # nested via dot-path
    assert "address.zip" in names
    assert "pets" in names
    pets_col = next(c for c in owner.columns if c.name == "pets")
    assert pets_col.dialect_specific.get("is_array") is True
    assert pets_col.dialect_specific.get("flag_for_d3") is True


def test_mongo_id_is_primary_key(petclinic_mongo_schema):
    spec = parse(petclinic_mongo_schema, "mongodb")
    owner = next(t for t in spec.tables if t.name == "owner")
    id_col = next(c for c in owner.columns if c.name == "_id")
    assert id_col.primary_key is True
    assert id_col.unique is True


def test_mongo_nullable_union_type():
    ddl = """{"collections": {"foo": {"$jsonSchema": {"properties": {
        "x": {"bsonType": ["string", "null"]}
    }}}}}"""
    spec = parse(ddl, "mongodb")
    assert isinstance(spec, SchemaSpec)
    col = spec.tables[0].columns[0]
    assert col.nullable is True


def test_mongo_invalid_json_returns_failure():
    res = parse("{not json", "mongodb")
    assert isinstance(res, ParseFailure)
    assert "JSON" in res.reason
