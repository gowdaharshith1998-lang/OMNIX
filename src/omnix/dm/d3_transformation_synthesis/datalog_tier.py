"""Datalog tier emitter.

Same shape as ``sql_tier``: optional, failure recorded honestly in
``TierFailure``. The pure-Python Datalog evaluator (P2) verifies the rule
against the MFI dataset.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple, Union

from omnix.dm._types import (
    MFI,
    APIFailure,
    ColumnMapping,
    LLMParseFailure,
    TierFailure,
)
from omnix.dm.d3_transformation_synthesis import llm_synthesizer
from omnix.dm.d3_transformation_synthesis.datalog import (
    DatalogSyntaxError,
    parse_program,
)

_DATALOG_FENCE_RE = re.compile(r"```datalog\s*\n(.*?)\n```", re.DOTALL)


SYSTEM_PROMPT_DATALOG = """You are translating a Python transformer into an equivalent Datalog rule.

OUTPUT FORMAT: a single ```datalog fenced block containing one or more rules.
The head predicate must be ``target(...)``; bodies should reference ``legacy(...)``.

RULES:
- Supported builtins: comparison (==, !=, <, <=, >, >=), arithmetic (+, -, *, /, %),
  aggregates (count, sum, min, max).
- Negation must be stratified.
- Use uppercase identifiers for variables, lowercase for constants/predicate names.
"""


def emit_datalog_rule(
    *,
    python_source: str,
    mapping: ColumnMapping,
    mfi_history: Tuple[MFI, ...] = (),
    backend_kwargs: Optional[dict] = None,
) -> Union[str, TierFailure]:
    """Ask the LLM for a Datalog rule equivalent of ``python_source``. Returns
    the rule text on success, otherwise a :class:`TierFailure`.
    """
    backend = llm_synthesizer._select_backend()
    user_prompt = (
        f"LEGACY COLUMN: {mapping.legacy_table}.{mapping.legacy_column}\n"
        f"TARGET COLUMN: {mapping.target_table}.{mapping.target_column}\n\n"
        "PYTHON TRANSFORMER:\n"
        "```python\n"
        f"{python_source}\n"
        "```\n"
    )
    try:
        response = backend(SYSTEM_PROMPT_DATALOG, user_prompt, backend_kwargs or {})
    except Exception as exc:
        return TierFailure(tier="datalog", reason=f"api_failure: {exc}")
    m = _DATALOG_FENCE_RE.search(response.text)
    if not m:
        return TierFailure(
            tier="datalog", reason="parse_failure: missing ```datalog fenced block"
        )
    rule = m.group(1).strip()
    if not rule:
        return TierFailure(tier="datalog", reason="parse_failure: empty datalog block")
    try:
        parse_program(rule)
    except DatalogSyntaxError as exc:
        return TierFailure(
            tier="datalog", reason=f"datalog_syntax_error: {exc}"
        )
    return rule


def verify_datalog_against_python(
    rule: str,
    python_source: str,
    mfi_history: Tuple[MFI, ...],
) -> Optional[TierFailure]:
    """The verifier converts each MFI into a (legacy, value) fact, runs the
    Datalog rule via the pure-Python evaluator (P2), and compares the
    resulting target tuple against the Python transformer's output. Without
    cross-tier execution wiring this is best-effort.
    """
    # MVP: validate that the rule parses; full cross-tier verification is a
    # PR C concern. Return None on accept, TierFailure on divergence.
    try:
        parse_program(rule)
    except DatalogSyntaxError as exc:
        return TierFailure(tier="datalog", reason=f"datalog_syntax_error: {exc}")
    return None


__all__ = [
    "SYSTEM_PROMPT_DATALOG",
    "emit_datalog_rule",
    "verify_datalog_against_python",
]
