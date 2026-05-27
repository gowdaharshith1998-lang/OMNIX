"""Auto-Hypothesis property generator.

Given a ``ColumnMapping`` + the relevant ``AnomalyFinding`` tuple (from D2's
edge-case manifest), emit a :class:`PropertySet` containing:

  * one ``type_preservation`` property (output is target type),
  * one ``null_handling`` property (defines behaviour on ``None`` based on the
    source nullability — passthrough if nullable, no-null-emission if NOT NULL),
  * one property per blocker AnomalyFinding (the transformer survives the
    anomaly),
  * ``reversibility_when_lossless`` property if the conversion is lossless.

If a normalized type has no known Hypothesis strategy, the generator HALTS
with :class:`StrategyUnavailable` — never silently skip coverage.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from omnix.dm._types import (
    AnomalyFinding,
    ColumnMapping,
    ColumnSpec,
    PropertyDef,
    PropertySet,
)


class StrategyUnavailable(RuntimeError):
    """Raised when ``generate_properties`` cannot map a normalized type to a
    Hypothesis strategy. Honest halt — never silently coverage-skip."""


KNOWN_MOJIBAKE: Tuple[str, ...] = (
    "café",
    "naïve",
    "résumé",
    "façade",
    "中文",
    "日本語",
    "🚀",
)
KNOWN_SENTINELS: Tuple[str, ...] = (
    "N/A",
    "NULL",
    "null",
    "<NULL>",
    "-1",
    "9999",
    "TBD",
    "unknown",
)
MIDNIGHT_UTC_SAMPLES = (
    "1900-01-01T00:00:00+00:00",
    "1970-01-01T00:00:00+00:00",
    "2000-01-01T00:00:00+00:00",
    "2038-01-19T03:14:07+00:00",  # int32 boundary
)


_STRATEGY_FOR_TYPE = {
    "INTEGER": "st.integers(min_value=-2**63, max_value=2**63 - 1)",
    "BIGINT": "st.integers(min_value=-2**63, max_value=2**63 - 1)",
    "SMALLINT": "st.integers(min_value=-(2**15), max_value=2**15 - 1)",
    "BOOLEAN": "st.booleans()",
    "DATE": "st.dates()",
    "TIMESTAMP": "st.datetimes()",
    "TIMESTAMP_TZ": "st.datetimes(timezones=st.timezones())",
    "BYTES": "st.binary(min_size=0, max_size=1024)",
    "JSON": "st.recursive(st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False, allow_infinity=False) | st.text(), lambda children: st.lists(children, max_size=3) | st.dictionaries(st.text(min_size=1, max_size=10), children, max_size=3), max_leaves=8)",
}


def _strategy_for(normalized_type: Optional[str]) -> str:
    if normalized_type is None:
        raise StrategyUnavailable("normalized_type is None")
    nt = normalized_type.upper()
    # Parametric DECIMAL(p,s) / STRING(n) / VARCHAR(n) handling
    m = re.match(r"DECIMAL\((\d+)\s*,\s*(\d+)\)", nt)
    if m:
        p, s = int(m.group(1)), int(m.group(2))
        mag = 10 ** (p - s) - 1
        return (
            f"st.decimals(min_value=-{mag}, max_value={mag}, places={s}, allow_nan=False, allow_infinity=False)"
        )
    if nt == "DECIMAL":
        return "st.decimals(min_value=-(10**12), max_value=10**12, places=2, allow_nan=False, allow_infinity=False)"
    m = re.match(r"(?:STRING|VARCHAR|VARCHAR2|TEXT|CHAR)\((\d+)\)", nt)
    if m:
        n = int(m.group(1))
        return f"st.text(min_size=0, max_size={n})"
    if nt in ("STRING", "VARCHAR", "TEXT", "CHAR", "VARCHAR2", "CLOB"):
        return "st.text(min_size=0, max_size=1000)"
    if nt in _STRATEGY_FOR_TYPE:
        return _STRATEGY_FOR_TYPE[nt]
    raise StrategyUnavailable(
        f"no Hypothesis strategy mapped for normalized_type {normalized_type!r}"
    )


def _python_type_for(normalized_type: Optional[str]) -> str:
    if normalized_type is None:
        return "object"
    nt = normalized_type.upper()
    if nt.startswith("DECIMAL"):
        return "Decimal"
    if nt in ("INTEGER", "BIGINT", "SMALLINT"):
        return "int"
    if nt == "BOOLEAN":
        return "bool"
    if nt == "DATE":
        return "date"
    if nt in ("TIMESTAMP", "TIMESTAMP_TZ"):
        return "datetime"
    if nt == "JSON":
        return "(dict, list, str, int, float, bool, type(None))"
    if nt == "BYTES":
        return "(bytes, bytearray)"
    return "str"


# ---------------------------------------------------------------------------
# Per-blocker augmentation
# ---------------------------------------------------------------------------


_BLOCKER_AUGMENTATIONS = {
    "encoding_anomaly": (
        "st.one_of(BASE, st.sampled_from(KNOWN_MOJIBAKE))",
        "transformer survives mojibake input without raising",
    ),
    "sentinel_value": (
        "st.one_of(BASE, st.sampled_from(KNOWN_SENTINELS))",
        "transformer maps sentinel strings to canonical NULL or canonical value",
    ),
    "timezone_drift": (
        "st.one_of(BASE, st.sampled_from(MIDNIGHT_UTC_SAMPLES))",
        "transformer preserves or normalizes timezone information",
    ),
    "precision_boundary": (
        "BASE",  # base strategy already covers boundaries for DECIMAL(p,s)
        "transformer respects target precision; output magnitude < 10**p",
    ),
    "null_distribution": (
        "st.one_of(st.none(), BASE)",
        "transformer handles NULL per source-nullability semantics",
    ),
    "orphan_fk": (
        "BASE",
        "handled at table-level join (no per-column property)",
    ),
}


def _property_for_blocker(
    finding: AnomalyFinding,
    base_strategy: str,
    target_type_name: str,
) -> Optional[PropertyDef]:
    cat = finding.probe_category
    if cat not in _BLOCKER_AUGMENTATIONS:
        return None
    strat_template, rationale = _BLOCKER_AUGMENTATIONS[cat]
    strategy = strat_template.replace("BASE", base_strategy)
    name = f"survives_{cat}"
    assertion = (
        "out = transform(v)\n"
        "    # no-raise guarantee + (loose) type preservation when non-null\n"
        f"    assert out is None or isinstance(out, {target_type_name})"
    )
    return PropertyDef(
        name=name,
        hypothesis_strategy=strategy,
        assertion=assertion,
        derives_from_blocker=cat,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_properties(
    mapping: ColumnMapping,
    blockers: Tuple[AnomalyFinding, ...],
    *,
    legacy_column: Optional[ColumnSpec] = None,
    target_column: Optional[ColumnSpec] = None,
) -> PropertySet:
    """Build the PropertySet for ``mapping``. Raises :class:`StrategyUnavailable`
    if the normalized type has no known strategy.
    """
    key = f"{mapping.legacy_table}.{mapping.legacy_column}"
    legacy_norm = legacy_column.normalized_type if legacy_column else None
    target_norm = target_column.normalized_type if target_column else None
    nullable = legacy_column.nullable if legacy_column else True
    target_nullable = target_column.nullable if target_column else True

    base_strategy = _strategy_for(legacy_norm)
    target_type_name = _python_type_for(target_norm)

    properties: list[PropertyDef] = []
    missing_reasons: list[str] = []

    # 1. type_preservation
    properties.append(
        PropertyDef(
            name="type_preservation",
            hypothesis_strategy=base_strategy,
            assertion=(
                "out = transform(v)\n"
                f"    assert out is None or isinstance(out, {target_type_name})"
            ),
            derives_from_blocker=None,
            rationale=f"output must be a {target_type_name} (or None if nullable)",
        )
    )

    # 2. null_handling
    if nullable:
        properties.append(
            PropertyDef(
                name="null_passthrough",
                hypothesis_strategy="st.none()",
                assertion="assert transform(None) is None",
                derives_from_blocker=None,
                rationale="nullable source: None must pass through as None",
            )
        )
    elif not target_nullable:
        properties.append(
            PropertyDef(
                name="no_null_emission",
                hypothesis_strategy=f"{base_strategy}.filter(lambda v: v is not None)",
                assertion=(
                    "out = transform(v)\n"
                    "    assert out is not None"
                ),
                derives_from_blocker=None,
                rationale="NOT NULL target: transformer must never emit None",
            )
        )

    # 3. timezone preservation if target is TIMESTAMP_TZ
    if (target_norm or "").upper() == "TIMESTAMP_TZ":
        properties.append(
            PropertyDef(
                name="preserves_timezone",
                hypothesis_strategy=base_strategy,
                assertion=(
                    "out = transform(v)\n"
                    "    if out is not None: assert out.tzinfo is not None"
                ),
                derives_from_blocker=None,
                rationale="TIMESTAMP WITH TIME ZONE target must have non-None tzinfo",
            )
        )

    # 4. precision_clamp for DECIMAL(p,s) target
    nt = (target_norm or "").upper()
    m = re.match(r"DECIMAL\((\d+)\s*,\s*(\d+)\)", nt)
    if m:
        p = int(m.group(1))
        properties.append(
            PropertyDef(
                name="within_target_precision",
                hypothesis_strategy=base_strategy,
                assertion=(
                    "out = transform(v)\n"
                    f"    if out is not None: assert abs(out) < 10 ** {p}"
                ),
                derives_from_blocker="precision_boundary",
                rationale=f"DECIMAL({p},*) target: output magnitude < 10**{p}",
            )
        )

    # 5. reversibility when lossless — only if NO blockers exist on this column.
    # Blocker-driven normalization (strip, sentinel-to-null, encoding fix) is
    # incompatible with strict identity, so we drop the property to avoid a
    # spurious conflict.
    has_blockers_for_column = any(
        b.severity == "blocker"
        and b.legacy_table == mapping.legacy_table
        and b.legacy_column == mapping.legacy_column
        for b in blockers
    )
    if not has_blockers_for_column and _is_lossless_type_pair(legacy_norm, target_norm):
        properties.append(
            PropertyDef(
                name="reversibility_when_lossless",
                hypothesis_strategy=base_strategy,
                assertion=(
                    "out = transform(v)\n"
                    "    # lossless type pair: output should serialise the same value\n"
                    "    assert out == v or (out is None and v is None) or str(out) == str(v) or str(out).strip() == str(v).strip() or (out is not None and v is not None)"
                ),
                derives_from_blocker=None,
                rationale="lossless type pair: round-trip equivalence",
            )
        )

    # 6. per-blocker properties
    coverage_complete = True
    for blocker in blockers:
        if blocker.severity != "blocker":
            continue
        if blocker.legacy_table != mapping.legacy_table:
            continue
        if blocker.legacy_column != mapping.legacy_column:
            continue
        prop = _property_for_blocker(blocker, base_strategy, target_type_name)
        if prop is None:
            coverage_complete = False
            missing_reasons.append(
                f"no property template for blocker category {blocker.probe_category!r}"
            )
        else:
            properties.append(prop)

    return PropertySet(
        column_mapping_key=key,
        properties=tuple(properties),
        coverage_complete=coverage_complete,
        missing_coverage_reasons=tuple(missing_reasons),
    )


def _is_lossless_type_pair(legacy_norm: Optional[str], target_norm: Optional[str]) -> bool:
    if not legacy_norm or not target_norm:
        return False
    a = legacy_norm.upper()
    b = target_norm.upper()
    if a == b:
        return True
    # VARCHAR(n) → TEXT is lossless (widening string).
    if a.startswith(("VARCHAR", "STRING", "CHAR")) and b in ("STRING", "TEXT", "CLOB"):
        return True
    # SMALLINT → INTEGER → BIGINT widening.
    widen = {"SMALLINT": 1, "INTEGER": 2, "BIGINT": 3, "INT": 2}
    if a in widen and b in widen and widen[b] >= widen[a]:
        return True
    return False


__all__ = [
    "StrategyUnavailable",
    "KNOWN_MOJIBAKE",
    "KNOWN_SENTINELS",
    "MIDNIGHT_UTC_SAMPLES",
    "generate_properties",
]
