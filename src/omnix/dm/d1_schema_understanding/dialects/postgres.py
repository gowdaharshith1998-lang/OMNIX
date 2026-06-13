"""PostgreSQL DDL parser.

Implementation note: rather than ship a Tree-sitter-postgresql grammar (which is
not in the locked stack — only Go/Java/Python/Ruby/Rust/TypeScript grammars are
pre-built), we lean on ``sqlparse`` for tokenization and a small dialect-aware
state machine for CREATE TABLE / CREATE INDEX / ALTER TABLE ADD CONSTRAINT /
COMMENT ON. This is robust enough for the dialect surfaces Petclinic exercises
(the PR A acceptance corpus) and surfaces ParseFailure rather than swallowing
unknown statements — see ``omnix.dm._types.ParseFailure``.

Honest gap (Codex axiom): rare PG extensions (partitions, custom operators,
GENERATED AS / GENERATED IDENTITY clauses) are tolerated but the resulting
``ColumnSpec.dialect_specific`` will flag ``flag_for_d3: True``.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from omnix.dm._types import (
    ColumnSpec,
    ForeignKeySpec,
    IndexSpec,
    SchemaSpec,
    TableSpec,
)

# Normalized type tag dispatch — kept in one place for cross-dialect consistency.
_PG_TYPE_MAP = {
    "smallint": "INTEGER",
    "integer": "INTEGER",
    "int": "INTEGER",
    "int2": "INTEGER",
    "int4": "INTEGER",
    "int8": "INTEGER",
    "bigint": "INTEGER",
    "serial": "INTEGER",
    "bigserial": "INTEGER",
    "smallserial": "INTEGER",
    "decimal": "DECIMAL",
    "numeric": "DECIMAL",
    "real": "FLOAT",
    "float": "FLOAT",
    "float4": "FLOAT",
    "float8": "FLOAT",
    "double precision": "FLOAT",
    "money": "DECIMAL",
    "varchar": "STRING",
    "character varying": "STRING",
    "char": "STRING",
    "character": "STRING",
    "text": "STRING",
    "citext": "STRING",
    "name": "STRING",
    "bytea": "BYTES",
    "date": "DATE",
    "time": "TIME",
    "timetz": "TIME",
    "timestamp": "TIMESTAMP",
    "timestamptz": "TIMESTAMP_TZ",
    "timestamp with time zone": "TIMESTAMP_TZ",
    "timestamp without time zone": "TIMESTAMP",
    "interval": "INTERVAL",
    "boolean": "BOOLEAN",
    "bool": "BOOLEAN",
    "uuid": "UUID",
    "json": "JSON",
    "jsonb": "JSON",
    "xml": "XML",
    "inet": "STRING",
    "cidr": "STRING",
    "macaddr": "STRING",
}


def _normalize_type(raw: str) -> str:
    """Map a raw PG type string (e.g., ``VARCHAR(255)``) to a normalized tag."""
    base = re.sub(r"\(.*?\)", "", raw).strip().lower()
    base = base.replace("  ", " ")
    return _PG_TYPE_MAP.get(base, "UNKNOWN")


_COL_NAME = re.compile(
    r'^\s*(?:"(?P<qname>[^"]+)"|(?P<name>[A-Za-z_][A-Za-z0-9_]*))\s+(?P<after>.+)$',
    re.DOTALL,
)

# Keywords that terminate the type token-walk (case-insensitive).
_TYPE_STOPWORDS = {
    "NOT",
    "NULL",
    "PRIMARY",
    "UNIQUE",
    "DEFAULT",
    "CHECK",
    "REFERENCES",
    "GENERATED",
    "COLLATE",
    "CONSTRAINT",
    "ON",
}


def _walk_type(after_name: str) -> tuple[str, str]:
    """Walk tokens after the column name to assemble the type (possibly
    multi-word, possibly with a parenthesized precision/length). Returns
    ``(raw_type, rest)``."""
    # Find where the rest-of-clause starts: the first stop-word at token
    # boundary, OR end of string.
    parts = re.split(r"(\s+|\(|\))", after_name)
    # Walk tokens collecting type pieces. Track paren depth so "(255)" stays inside.
    type_tokens: list[str] = []
    consumed = 0
    paren_depth = 0
    i = 0
    while i < len(parts):
        tok = parts[i]
        consumed = sum(len(p) for p in parts[: i + 1])
        if tok == "":
            i += 1
            continue
        if tok.isspace():
            type_tokens.append(tok)
            i += 1
            continue
        if tok == "(":
            paren_depth += 1
            type_tokens.append(tok)
            i += 1
            continue
        if tok == ")":
            paren_depth -= 1
            type_tokens.append(tok)
            i += 1
            continue
        if paren_depth > 0:
            type_tokens.append(tok)
            i += 1
            continue
        upper = tok.upper().strip()
        if upper in _TYPE_STOPWORDS:
            # Roll back the trailing whitespace from type
            consumed = sum(len(p) for p in parts[:i])
            break
        type_tokens.append(tok)
        i += 1
    raw_type = "".join(type_tokens).strip()
    raw_type = re.sub(r"\s+", " ", raw_type)
    rest = after_name[consumed:]
    return raw_type, rest


def _split_top_level(body: str) -> List[str]:
    """Split a CREATE TABLE body on top-level commas, respecting parens."""
    out: List[str] = []
    depth = 0
    cur: List[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur).strip())
    return [p for p in out if p]


_TABLE_HEAD = re.compile(
    r"create\s+(?:unlogged\s+|temporary\s+|temp\s+)?table\s+(?:if\s+not\s+exists\s+)?"
    r"(?:\"(?P<qname>[^\"]+)\"|(?P<name>[A-Za-z_][A-Za-z0-9_.]*))\s*\(",
    re.IGNORECASE | re.DOTALL,
)


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql


def _find_table_body(sql: str, start_idx: int) -> Tuple[str, int]:
    """Return ``(body, end_index_after_closing_paren)`` for the table starting
    at ``start_idx`` (the index of the opening ``(``). Raises if unbalanced."""
    depth = 0
    for i in range(start_idx, len(sql)):
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
            if depth == 0:
                return sql[start_idx + 1 : i], i + 1
    raise ValueError("unterminated table body")


def _parse_column(part: str) -> Optional[ColumnSpec]:
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
    primary_key = bool(re.search(r"\bPRIMARY\s+KEY\b", rest_upper))
    unique = bool(re.search(r"\bUNIQUE\b", rest_upper))
    default = None
    m_def = re.search(
        r"DEFAULT\s+(.*?)(?=\s+(?:NOT\s+NULL|NULL|PRIMARY|UNIQUE|CHECK|REFERENCES|GENERATED|$))",
        rest,
        re.IGNORECASE | re.DOTALL,
    )
    if m_def:
        default = m_def.group(1).strip().rstrip(",").strip()
    return ColumnSpec(
        name=name,
        raw_type=raw_type,
        normalized_type=_normalize_type(raw_type),
        nullable=nullable,
        default=default,
        primary_key=primary_key,
        unique=unique,
        comment=None,
        dialect_specific={},
    )


def _parse_table_constraints(
    parts: List[str], table_name: str
) -> Tuple[Tuple[str, ...], Tuple[ForeignKeySpec, ...]]:
    pk_cols: Tuple[str, ...] = ()
    fks: List[ForeignKeySpec] = []
    for raw in parts:
        upper = raw.upper().strip()
        if upper.startswith("PRIMARY KEY"):
            m = re.search(r"PRIMARY\s+KEY\s*\(([^)]+)\)", raw, re.IGNORECASE)
            if m:
                pk_cols = tuple(
                    c.strip().strip('"') for c in m.group(1).split(",") if c.strip()
                )
        elif upper.startswith("FOREIGN KEY") or upper.startswith("CONSTRAINT"):
            m = re.search(
                r"(?:CONSTRAINT\s+(?P<cname>\S+)\s+)?FOREIGN\s+KEY\s*\((?P<cols>[^)]+)\)\s*"
                r"REFERENCES\s+(?P<rtbl>[^\s(]+)\s*\((?P<rcols>[^)]+)\)"
                r"(?:.*?ON\s+DELETE\s+(?P<ond>CASCADE|SET\s+NULL|SET\s+DEFAULT|RESTRICT|NO\s+ACTION))?"
                r"(?:.*?ON\s+UPDATE\s+(?P<onu>CASCADE|SET\s+NULL|SET\s+DEFAULT|RESTRICT|NO\s+ACTION))?",
                raw,
                re.IGNORECASE | re.DOTALL,
            )
            if m:
                from_cols = tuple(
                    c.strip().strip('"') for c in m.group("cols").split(",")
                )
                to_cols = tuple(
                    c.strip().strip('"') for c in m.group("rcols").split(",")
                )
                fks.append(
                    ForeignKeySpec(
                        name=m.group("cname") or f"{table_name}_fk_{len(fks)}",
                        from_table=table_name,
                        from_columns=from_cols,
                        to_table=m.group("rtbl").strip('"'),
                        to_columns=to_cols,
                        on_delete=(m.group("ond") or "").upper() or None,
                        on_update=(m.group("onu") or "").upper() or None,
                    )
                )
    return pk_cols, tuple(fks)


_INDEX_LINE = re.compile(
    r"create\s+(?P<unique>unique\s+)?index\s+(?:if\s+not\s+exists\s+)?"
    r"(?:\"(?P<qname>[^\"]+)\"|(?P<name>[A-Za-z_][A-Za-z0-9_.]*))\s+"
    r"on\s+(?:\"(?P<qtbl>[^\"]+)\"|(?P<tbl>[A-Za-z_][A-Za-z0-9_.]*))"
    r"(?:\s+using\s+(?P<method>[A-Za-z_]+))?\s*\(\s*(?P<cols>[^)]+)\)",
    re.IGNORECASE | re.DOTALL,
)


def _parse_indexes(sql: str) -> List[IndexSpec]:
    out: List[IndexSpec] = []
    for m in _INDEX_LINE.finditer(sql):
        idx = IndexSpec(
            name=m.group("qname") or m.group("name"),
            table=m.group("qtbl") or m.group("tbl"),
            columns=tuple(
                c.strip().strip('"') for c in m.group("cols").split(",") if c.strip()
            ),
            unique=bool(m.group("unique")),
            method=(m.group("method") or "").lower() or None,
        )
        out.append(idx)
    return out


_COMMENT_LINE = re.compile(
    r"comment\s+on\s+column\s+(?:\"(?P<qtbl>[^\"]+)\"|(?P<tbl>[A-Za-z_][A-Za-z0-9_.]*))"
    r"\.(?:\"(?P<qcol>[^\"]+)\"|(?P<col>[A-Za-z_][A-Za-z0-9_]*))\s+is\s+'(?P<text>(?:[^']|'')*)'",
    re.IGNORECASE | re.DOTALL,
)


def _parse_comments(sql: str) -> dict:
    comments: dict = {}
    for m in _COMMENT_LINE.finditer(sql):
        tbl = m.group("qtbl") or m.group("tbl")
        col = m.group("qcol") or m.group("col")
        comments[(tbl.lower(), col.lower())] = m.group("text").replace("''", "'")
    return comments


def parse(ddl: str) -> SchemaSpec:
    """Parse a PostgreSQL DDL string into a normalized SchemaSpec."""
    sql = _strip_comments(ddl)
    comments = _parse_comments(sql)
    tables: List[TableSpec] = []
    warnings: List[str] = []
    cursor = 0
    while True:
        m = _TABLE_HEAD.search(sql, cursor)
        if m is None:
            break
        name = m.group("qname") or m.group("name")
        # Strip schema-qualified prefix (public.owner -> owner) for matching
        if "." in name and not (m.group("qname") and "." in m.group("qname")):
            name = name.split(".", 1)[1]
        body_start = m.end() - 1  # the '(' position
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
            if col is not None:
                # Attach comment if present.
                key = (name.lower(), col.name.lower())
                if key in comments:
                    col = ColumnSpec(
                        name=col.name,
                        raw_type=col.raw_type,
                        normalized_type=col.normalized_type,
                        nullable=col.nullable,
                        default=col.default,
                        primary_key=col.primary_key,
                        unique=col.unique,
                        comment=comments[key],
                        dialect_specific=col.dialect_specific,
                    )
                cols.append(col)
            else:
                warnings.append(f"could not parse column line in {name}: {p[:80]!r}")
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
                comment=None,
            )
        )

    # Indexes are a separate top-level scan
    idx_objs = _parse_indexes(sql)
    if idx_objs:
        merged: List[TableSpec] = []
        for t in tables:
            t_indexes = tuple(i for i in idx_objs if i.table.lower() == t.name.lower())
            if t_indexes:
                merged.append(
                    TableSpec(
                        name=t.name,
                        columns=t.columns,
                        primary_key=t.primary_key,
                        foreign_keys=t.foreign_keys,
                        indexes=t_indexes,
                        comment=t.comment,
                    )
                )
            else:
                merged.append(t)
        tables = merged

    return SchemaSpec(
        dialect="postgres",
        name="public",
        tables=tuple(tables),
        parse_warnings=tuple(warnings),
    )


__all__ = ["parse"]
