"""MongoDB collection-schema parser.

Input is a JSON Schema (the body of Mongo's ``$jsonSchema`` validator). We map
each collection to a ``TableSpec`` and each top-level (or dotted-path nested)
property to a ``ColumnSpec``. Arrays are flagged in ``dialect_specific``;
PR B / PR C own normalization into relational shape.

Two acceptable input shapes:
  1. ``{"collections": {"<name>": {"$jsonSchema": {...}}, ...}}``
  2. ``{"<name>": {"$jsonSchema": {...}}, ...}`` (legacy form)
"""

from __future__ import annotations

import json
from typing import Iterator, List, Optional, Tuple

from omnix.dm._types import ColumnSpec, SchemaSpec, TableSpec

_BSON_TYPE_MAP = {
    "objectId": "STRING",
    "string": "STRING",
    "int": "INTEGER",
    "long": "INTEGER",
    "double": "FLOAT",
    "decimal": "DECIMAL",
    "bool": "BOOLEAN",
    "boolean": "BOOLEAN",
    "date": "TIMESTAMP",
    "timestamp": "TIMESTAMP",
    "object": "JSON",
    "array": "JSON",
    "binData": "BYTES",
    "null": "UNKNOWN",
    "regex": "STRING",
    "javascript": "STRING",
    "minKey": "UNKNOWN",
    "maxKey": "UNKNOWN",
}


def _bson_type_for(prop: dict) -> str:
    """Best-effort: return a single bsonType string for a JSON-Schema property."""
    bt = prop.get("bsonType")
    if isinstance(bt, list):
        # multi-type — pick first non-null for normalization, surface the rest
        for t in bt:
            if t != "null":
                return t
        return "null"
    if isinstance(bt, str):
        return bt
    # Fall back to JSON Schema "type"
    t = prop.get("type")
    if isinstance(t, list):
        for t2 in t:
            if t2 != "null":
                return t2
        return "null"
    if isinstance(t, str):
        return t
    return "object"


def _walk_properties(
    props: dict, required: List[str], path: str = ""
) -> Iterator[Tuple[str, dict, bool]]:
    """Yield ``(dotted_path, prop_schema, is_required)``. Recursively descends
    into nested ``object`` properties, joining via ``.``."""
    for name, prop in props.items():
        full = f"{path}.{name}" if path else name
        bt = _bson_type_for(prop)
        is_req = name in required
        yield full, prop, is_req
        if bt == "object" and isinstance(prop.get("properties"), dict):
            yield from _walk_properties(
                prop["properties"], prop.get("required", []), full
            )


def _normalize_collections(parsed: dict) -> dict:
    if "collections" in parsed and isinstance(parsed["collections"], dict):
        return parsed["collections"]
    # legacy form: top-level keys are collection names
    return parsed


def _column_from_property(
    name: str, prop: dict, is_required: bool
) -> ColumnSpec:
    bt = _bson_type_for(prop)
    raw = bt
    if "bsonType" in prop and isinstance(prop["bsonType"], list):
        raw = "|".join(prop["bsonType"])
    norm = _BSON_TYPE_MAP.get(bt, "UNKNOWN")
    dialect_specific: dict = {"bson_type": raw}
    if bt == "array":
        dialect_specific["is_array"] = True
        dialect_specific["flag_for_d3"] = True
        if "items" in prop:
            dialect_specific["array_item_type"] = _bson_type_for(prop["items"])
    if isinstance(prop.get("bsonType"), list) and "null" in prop["bsonType"]:
        nullable = True
    else:
        nullable = not is_required
    return ColumnSpec(
        name=name,
        raw_type=raw,
        normalized_type=norm,
        nullable=nullable,
        default=None,
        primary_key=(name == "_id"),
        unique=(name == "_id"),
        comment=prop.get("description"),
        dialect_specific=dialect_specific,
    )


def parse(ddl_or_json: str) -> SchemaSpec:
    """Parse a Mongo schema description (JSON string) into a SchemaSpec.

    Raises ``json.JSONDecodeError`` on malformed JSON — callers should treat
    that as a ParseFailure equivalent (see ``ddl_parser.parse`` dispatcher).
    """
    parsed = json.loads(ddl_or_json)
    collections = _normalize_collections(parsed)
    tables: List[TableSpec] = []
    warnings: List[str] = []
    for cname, cdef in collections.items():
        if not isinstance(cdef, dict):
            warnings.append(f"collection {cname} has non-dict definition")
            continue
        schema = cdef.get("$jsonSchema") or cdef
        if not isinstance(schema, dict):
            warnings.append(f"collection {cname} missing $jsonSchema")
            continue
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict):
            warnings.append(f"collection {cname} has invalid properties")
            continue
        cols: List[ColumnSpec] = []
        for full_path, prop, is_req in _walk_properties(properties, required):
            cols.append(_column_from_property(full_path, prop, is_req))
        tables.append(
            TableSpec(
                name=cname,
                columns=tuple(cols),
                primary_key=tuple(c.name for c in cols if c.primary_key),
                foreign_keys=(),
                indexes=(),
            )
        )
    return SchemaSpec(
        dialect="mongodb",
        name="default",
        tables=tuple(tables),
        parse_warnings=tuple(warnings),
    )


__all__ = ["parse"]
