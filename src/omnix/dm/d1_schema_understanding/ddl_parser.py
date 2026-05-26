"""Top-level DDL parser dispatcher.

Per the EARS contract: when a DDL string is passed in we either return a
fully-formed ``SchemaSpec`` or — explicitly — a ``ParseFailure`` record. We
never silently swallow an unparseable statement; the Codex axiom requires
that unrecognised input surface as a first-class output.
"""

from __future__ import annotations

import json
from typing import Union

from omnix.dm._types import Dialect, ParseFailure, SchemaSpec
from omnix.dm.d1_schema_understanding.dialects import (
    mongodb,
    mysql,
    oracle,
    postgres,
)

_DISPATCH = {
    "postgres": postgres.parse,
    "mysql": mysql.parse,
    "oracle": oracle.parse,
    "mongodb": mongodb.parse,
}


def parse(ddl: str, dialect: Dialect) -> Union[SchemaSpec, ParseFailure]:
    """Dispatch ``ddl`` to the right dialect parser. Catches parser-level
    exceptions and re-emits them as ``ParseFailure`` so callers never receive
    a partially-constructed SchemaSpec."""
    if not isinstance(ddl, str):
        return ParseFailure(
            dialect=dialect, reason=f"ddl must be str, got {type(ddl).__name__}"
        )
    if not isinstance(dialect, str) or dialect not in _DISPATCH:
        return ParseFailure(
            dialect=dialect if isinstance(dialect, str) else "postgres",  # type: ignore[arg-type]
            reason=f"unknown dialect: {dialect!r}",
        )
    if not ddl.strip():
        return ParseFailure(dialect=dialect, reason="empty DDL")
    try:
        spec = _DISPATCH[dialect](ddl)
    except json.JSONDecodeError as e:
        return ParseFailure(
            dialect=dialect, reason=f"invalid JSON: {e.msg}", location=f"line {e.lineno}"
        )
    except Exception as e:  # noqa: BLE001 — explicit surfacing per Codex axiom
        return ParseFailure(
            dialect=dialect,
            reason=f"{type(e).__name__}: {e}",
        )
    # Strict: a SchemaSpec with zero tables on a non-empty DDL is suspicious.
    if not spec.tables and dialect != "mongodb":
        return ParseFailure(
            dialect=dialect,
            reason="no CREATE TABLE statement parsed from non-empty DDL",
        )
    return spec


__all__ = ["parse"]
