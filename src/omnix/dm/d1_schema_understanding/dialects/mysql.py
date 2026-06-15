"""MySQL DDL parser. Shares state-machine logic with the Postgres parser via a
common helper module, but maps types and identifier quoting per MySQL semantics.

Handles backtick-quoted identifiers, ENGINE=..., CHARACTER SET, COLLATE, and
AUTO_INCREMENT. Surfaces ParseFailure on unbalanced bodies (honesty invariant).
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

_MYSQL_TYPE_MAP = {
    "tinyint": "INTEGER",
    "smallint": "INTEGER",
    "mediumint": "INTEGER",
    "int": "INTEGER",
    "integer": "INTEGER",
    "bigint": "INTEGER",
    "decimal": "DECIMAL",
    "numeric": "DECIMAL",
    "float": "FLOAT",
    "double": "FLOAT",
    "real": "FLOAT",
    "bit": "INTEGER",
    "char": "STRING",
    "varchar": "STRING",
    "tinytext": "STRING",
    "text": "STRING",
    "mediumtext": "STRING",
    "longtext": "STRING",
    "enum": "STRING",
    "set": "STRING",
    "binary": "BYTES",
    "varbinary": "BYTES",
    "tinyblob": "BYTES",
    "blob": "BYTES",
    "mediumblob": "BYTES",
    "longblob": "BYTES",
    "date": "DATE",
    "time": "TIME",
    "datetime": "TIMESTAMP",
    "timestamp": "TIMESTAMP",
    "year": "INTEGER",
    "json": "JSON",
    "boolean": "BOOLEAN",
    "bool": "BOOLEAN",
}


def _normalize_type(raw: str) -> str:
    base = re.sub(r"\(.*?\)", "", raw).strip().lower().split()[0]
    return _MYSQL_TYPE_MAP.get(base, "UNKNOWN")


_TABLE_HEAD = re.compile(
    r"create\s+(?:temporary\s+)?table\s+(?:if\s+not\s+exists\s+)?"
    r"(?:`(?P<bname>[^`]+)`|(?P<name>[A-Za-z_][A-Za-z0-9_.]*))\s*\(",
    re.IGNORECASE | re.DOTALL,
)

_COL_NAME = re.compile(
    r"^\s*(?:`(?P<bname>[^`]+)`|(?P<name>[A-Za-z_][A-Za-z0-9_]*))\s+(?P<after>.+)$",
    re.DOTALL,
)

_MYSQL_STOPWORDS = {
    "NOT",
    "NULL",
    "PRIMARY",
    "UNIQUE",
    "DEFAULT",
    "CHECK",
    "REFERENCES",
    "AUTO_INCREMENT",
    "COMMENT",
    "COLLATE",
    "CHARACTER",
    "ON",
    "CONSTRAINT",
    "GENERATED",
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
        if upper in _MYSQL_STOPWORDS:
            consumed = sum(len(p) for p in parts[:i])
            break
        # UNSIGNED is a type-modifier in MySQL, keep walking past it
        if upper == "UNSIGNED":
            type_tokens.append(tok)
            continue
        type_tokens.append(tok)
    raw_type = re.sub(r"\s+", " ", "".join(type_tokens)).strip()
    rest = after_name[consumed:]
    return raw_type, rest


def _parse_column(part: str) -> ColumnSpec | None:
    m = _COL_NAME.match(part)
    if m is None:
        return None
    name = m.group("bname") or m.group("name")
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
        r"DEFAULT\s+(.*?)(?=\s+(?:NOT\s+NULL|NULL|AUTO_INCREMENT|UNIQUE|PRIMARY|COMMENT|ON\s+UPDATE|$))",
        rest,
        re.IGNORECASE | re.DOTALL,
    )
    if m_def:
        default = m_def.group(1).strip().rstrip(",").strip()
    dialect_specific: dict = {}
    m_charset = re.search(r"CHARACTER\s+SET\s+(\S+)", rest, re.IGNORECASE)
    if m_charset:
        dialect_specific["charset"] = m_charset.group(1)
    m_collate = re.search(r"COLLATE\s+(\S+)", rest, re.IGNORECASE)
    if m_collate:
        dialect_specific["collate"] = m_collate.group(1)
    if "AUTO_INCREMENT" in rest_upper:
        dialect_specific["auto_increment"] = True
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
        name = m.group("bname") or m.group("name")
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
                or upper.startswith("KEY")
                or upper.startswith("INDEX")
                or upper.startswith("FULLTEXT")
                or upper.startswith("CHECK")
            ):
                continue
            col = _parse_column(p)
            if col is None:
                warnings.append(f"could not parse column line in {name}: {p[:80]!r}")
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
    return SchemaSpec(
        dialect="mysql",
        name="default",
        tables=tuple(tables),
        parse_warnings=tuple(warnings),
    )


__all__ = ["parse"]
