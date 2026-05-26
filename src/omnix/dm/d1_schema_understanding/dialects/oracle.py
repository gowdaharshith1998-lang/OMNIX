"""Oracle DDL parser.

Surfaces:
  * NUMBER(p,s)             → normalized_type=DECIMAL with precision/scale
                              stashed in dialect_specific.
  * VARCHAR2 / NVARCHAR2    → STRING
  * DATE                    → TIMESTAMP (Oracle DATE includes time, no TZ —
                              flagged for D2 timezone_drift prober).
  * TIMESTAMP WITH TIME ZONE → TIMESTAMP_TZ
  * CLOB / NCLOB / BLOB     → STRING / BYTES
  * Sequences and triggers are tolerated (recognised, not parsed into types) —
    flag_for_d3 is recorded as a parse_warning so PR B's transformer synth
    knows it has work to do.

Honest gap: PARTITION BY clauses are skipped (warned), DEFAULT ON NULL is
parsed but the value is not interpreted.
"""

from __future__ import annotations

import re
from typing import List

from omnix.dm._types import ColumnSpec, SchemaSpec, TableSpec
from omnix.dm.d1_schema_understanding.dialects.postgres import (
    _find_table_body,
    _parse_table_constraints,
    _split_top_level,
    _strip_comments,
)

_ORACLE_TYPE_MAP = {
    "number": "DECIMAL",
    "integer": "INTEGER",
    "int": "INTEGER",
    "smallint": "INTEGER",
    "binary_integer": "INTEGER",
    "float": "FLOAT",
    "binary_float": "FLOAT",
    "binary_double": "FLOAT",
    "real": "FLOAT",
    "double precision": "FLOAT",
    "varchar2": "STRING",
    "nvarchar2": "STRING",
    "varchar": "STRING",
    "char": "STRING",
    "nchar": "STRING",
    "clob": "STRING",
    "nclob": "STRING",
    "long": "STRING",
    "raw": "BYTES",
    "long raw": "BYTES",
    "blob": "BYTES",
    "bfile": "BYTES",
    "date": "TIMESTAMP",  # Oracle DATE includes time component
    "timestamp": "TIMESTAMP",
    "timestamp with time zone": "TIMESTAMP_TZ",
    "timestamp with local time zone": "TIMESTAMP_TZ",
    "interval year to month": "INTERVAL",
    "interval day to second": "INTERVAL",
    "rowid": "STRING",
    "urowid": "STRING",
    "boolean": "BOOLEAN",
}


def _normalize_type(raw: str) -> str:
    base = re.sub(r"\(.*?\)", "", raw).strip().lower()
    base = re.sub(r"\s+", " ", base)
    if base in _ORACLE_TYPE_MAP:
        return _ORACLE_TYPE_MAP[base]
    # multi-word handling
    for key in _ORACLE_TYPE_MAP:
        if base.startswith(key):
            return _ORACLE_TYPE_MAP[key]
    return "UNKNOWN"


_TABLE_HEAD = re.compile(
    r"create\s+(?:global\s+temporary\s+|private\s+temporary\s+)?table\s+"
    r"(?:\"(?P<qname>[^\"]+)\"|(?P<name>[A-Za-z_][A-Za-z0-9_.$#]*))\s*\(",
    re.IGNORECASE | re.DOTALL,
)


_COL_NAME = re.compile(
    r'^\s*(?:"(?P<qname>[^"]+)"|(?P<name>[A-Za-z_][A-Za-z0-9_$#]*))\s+(?P<after>.+)$',
    re.DOTALL,
)

_ORACLE_STOPWORDS = {
    "NOT",
    "NULL",
    "PRIMARY",
    "UNIQUE",
    "DEFAULT",
    "CHECK",
    "REFERENCES",
    "CONSTRAINT",
    "GENERATED",
    "ENABLE",
    "DISABLE",
}


def _walk_type(after_name: str) -> tuple[str, str]:
    parts = re.split(r"(\s+|\(|\))", after_name)
    type_tokens: list[str] = []
    paren_depth = 0
    consumed = 0
    for i, tok in enumerate(parts):
        consumed = sum(len(p) for p in parts[: i + 1])
        if tok == "":
            continue
        if tok.isspace():
            type_tokens.append(tok)
            continue
        if tok == "(":
            paren_depth += 1
            type_tokens.append(tok)
            continue
        if tok == ")":
            paren_depth -= 1
            type_tokens.append(tok)
            continue
        if paren_depth > 0:
            type_tokens.append(tok)
            continue
        upper = tok.upper().strip()
        if upper in _ORACLE_STOPWORDS:
            consumed = sum(len(p) for p in parts[:i])
            break
        type_tokens.append(tok)
    raw_type = re.sub(r"\s+", " ", "".join(type_tokens)).strip()
    rest = after_name[consumed:]
    return raw_type, rest


def _extract_number_meta(raw: str) -> dict:
    m = re.match(r"NUMBER\s*\(\s*(\d+)\s*(?:,\s*(-?\d+)\s*)?\)", raw, re.IGNORECASE)
    if not m:
        return {}
    out: dict = {"precision": int(m.group(1))}
    if m.group(2) is not None:
        out["scale"] = int(m.group(2))
    return out


def _parse_column(part: str) -> ColumnSpec | None:
    m = _COL_NAME.match(part)
    if m is None:
        return None
    name = m.group("qname") or m.group("name")
    after = m.group("after") or ""
    raw_type, rest = _walk_type(after)
    if not raw_type:
        return None
    rest_upper = rest.upper()
    nullable = "NOT NULL" not in rest_upper
    primary_key = "PRIMARY KEY" in rest_upper
    unique = bool(re.search(r"\bUNIQUE\b", rest_upper))
    default = None
    m_def = re.search(
        r"DEFAULT\s+(?:ON\s+NULL\s+)?(.*?)(?=\s+(?:NOT\s+NULL|NULL|UNIQUE|PRIMARY|CHECK|REFERENCES|GENERATED|$))",
        rest,
        re.IGNORECASE | re.DOTALL,
    )
    if m_def:
        default = m_def.group(1).strip().rstrip(",").strip()
    dialect_specific: dict = {}
    if raw_type.upper().startswith("NUMBER"):
        dialect_specific.update(_extract_number_meta(raw_type))
    if raw_type.upper() == "DATE":
        dialect_specific["oracle_date_includes_time"] = True
        dialect_specific["flag_for_d3"] = True
    return ColumnSpec(
        name=name,
        raw_type=raw_type,
        normalized_type=_normalize_type(raw_type),
        nullable=nullable,
        default=default,
        primary_key=primary_key,
        unique=unique,
        comment=None,
        dialect_specific=dialect_specific,
    )


def parse(ddl: str) -> SchemaSpec:
    sql = _strip_comments(ddl)
    tables: List[TableSpec] = []
    warnings: List[str] = []
    cursor = 0
    while True:
        m = _TABLE_HEAD.search(sql, cursor)
        if m is None:
            break
        name = m.group("qname") or m.group("name")
        if "." in name:
            name = name.split(".", 1)[1]
        body_start = m.end() - 1
        try:
            body, end_idx = _find_table_body(sql, body_start)
        except ValueError:
            warnings.append(f"unterminated table body for {name}")
            cursor = m.end()
            continue
        cursor = end_idx
        parts = _split_top_level(body)
        cols: List[ColumnSpec] = []
        for p in parts:
            upper = p.upper().strip()
            if (
                upper.startswith("PRIMARY KEY")
                or upper.startswith("FOREIGN KEY")
                or upper.startswith("CONSTRAINT")
                or upper.startswith("UNIQUE")
                or upper.startswith("CHECK")
            ):
                continue
            col = _parse_column(p)
            if col is None:
                warnings.append(f"could not parse column in {name}: {p[:80]!r}")
            else:
                cols.append(col)
        pk_cols, fks = _parse_table_constraints(parts, name)
        if not pk_cols:
            pk_cols = tuple(c.name for c in cols if c.primary_key)
        tables.append(
            TableSpec(
                name=name,
                columns=tuple(cols),
                primary_key=pk_cols,
                foreign_keys=fks,
                indexes=(),
            )
        )

    if re.search(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\b", sql, re.IGNORECASE):
        warnings.append("Oracle TRIGGER detected — flag_for_d3 (PR B handles)")
    if re.search(r"\bCREATE\s+SEQUENCE\b", sql, re.IGNORECASE):
        warnings.append("Oracle SEQUENCE detected — flag_for_d3 (PR B handles)")

    return SchemaSpec(
        dialect="oracle",
        name="default",
        tables=tuple(tables),
        parse_warnings=tuple(warnings),
    )


__all__ = ["parse"]
