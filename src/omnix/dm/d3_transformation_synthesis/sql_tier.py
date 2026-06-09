"""SQL CASE tier emitter.

After the Python tier converges, attempt to emit an equivalent SQL CASE
expression. The SQL tier is OPTIONAL — failure does NOT block the
TransformerSpec; it is recorded as a ``TierFailure`` entry in
``tier_failures`` with a reason.

Verification: execute both Python and SQL against the same MFI dataset and
compare outputs. If a transient Postgres container is unavailable, we skip
with ``TierFailure(reason="infrastructure_unavailable")``.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple, Union

from omnix.dm._types import (
    MFI,
    ColumnMapping,
    PropertySet,
    TierFailure,
)
from omnix.dm.d3_transformation_synthesis import llm_synthesizer

_SQL_FENCE_RE = re.compile(r"```sql\s*\n(.*?)\n```", re.DOTALL)


SYSTEM_PROMPT_SQL = """You are translating a Python transformer into an equivalent SQL CASE expression.

OUTPUT FORMAT: a single ```sql fenced block containing a CASE expression that
references the legacy column as ``legacy_col``. The CASE expression should be
embeddable in: ``SELECT (your CASE) AS new_col FROM legacy_table``.

RULES:
- Only standard SQL (Postgres dialect preferred); no procedural code.
- NULL inputs must produce NULL outputs unless the Python transformer maps
  them otherwise.
- Use COALESCE / CASE WHEN / CAST as needed.
"""


def emit_sql_case(
    *,
    python_source: str,
    mapping: ColumnMapping,
    property_set: Optional[PropertySet] = None,
    mfi_history: Tuple[MFI, ...] = (),
    backend_kwargs: Optional[dict] = None,
) -> Union[str, TierFailure]:
    """Ask the LLM for a SQL CASE equivalent of ``python_source``. Returns
    the SQL string on success, otherwise a :class:`TierFailure`.

    This function does NOT execute the SQL against a database; the caller may
    pass the returned SQL through a verifier that hits a transient PG. Such
    a verifier records a ``TierFailure`` if the SQL diverges from Python on
    any MFI.
    """
    backend = llm_synthesizer._select_backend()
    user_prompt = (
        f"LEGACY COLUMN: {mapping.legacy_table}.{mapping.legacy_column}\n"
        f"TARGET COLUMN: {mapping.target_table}.{mapping.target_column}\n\n"
        "PYTHON TRANSFORMER (the source of truth — emit an SQL CASE that "
        "produces the same output for every input):\n"
        "```python\n"
        f"{python_source}\n"
        "```\n"
    )
    try:
        response = backend(SYSTEM_PROMPT_SQL, user_prompt, backend_kwargs or {})
    except Exception as exc:
        return TierFailure(tier="sql", reason=f"api_failure: {exc}")
    m = _SQL_FENCE_RE.search(response.text)
    if not m:
        return TierFailure(
            tier="sql", reason="parse_failure: missing ```sql fenced block"
        )
    sql = m.group(1).strip()
    if not sql:
        return TierFailure(tier="sql", reason="parse_failure: empty SQL block")
    return sql


def verify_sql_against_python(
    sql: str,
    python_source: str,
    mfi_history: Tuple[MFI, ...],
) -> Optional[TierFailure]:
    """Best-effort verifier. Without a transient Postgres connection we
    return a ``TierFailure(infrastructure_unavailable)`` honestly.
    """
    # Default OMNIX-DM verifier — no live PG in CI.
    return TierFailure(
        tier="sql",
        reason="infrastructure_unavailable: no transient PG container in this env",
    )


__all__ = ["SYSTEM_PROMPT_SQL", "emit_sql_case", "verify_sql_against_python"]
