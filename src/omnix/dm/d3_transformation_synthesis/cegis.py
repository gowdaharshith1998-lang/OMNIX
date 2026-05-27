"""Migrator-style CEGIS layer + SketchLibrary.

Academic provenance:
  * Migrator (arXiv 1904.05498, Wang/Dillig 2019) — three-stage decomposition:
    (1) value correspondence (PR A did this), (2) sketch generation,
    (3) enumerative search with minimum failing input (MFI) pruning.
  * Reflexion (Shinn et al., NeurIPS 2023) — structural pattern.
  * Huang ICLR 2024 — intrinsic self-correction fragile; PR B grounds critique in MFI.
  * Property-Generated Solver (arXiv 2506.18315) — 23–37% pass@1 over TDD.

PR B's twist: the LLM is the "synthesizer" (no enumeration), and sketches are
PROMPT HINTS, not template-instantiation candidates. SketchLibrary serves two
purposes: (a) prime the LLM with known-good shapes, (b) record which patterns
the LLM tried + which failed (pruned).
"""

from __future__ import annotations

from typing import Tuple, Union

from omnix.dm._types import (
    AnomalyFinding,
    ColumnMapping,
    ColumnSpec,
    PropertySet,
    ReflexionHalt,
    ReflexionSuccess,
    SketchHint,
)
from omnix.dm.d3_transformation_synthesis.reflexion_loop import LoopInputs, run


SKETCHES: Tuple[SketchHint, ...] = (
    SketchHint(
        sketch_id="varchar_to_text_passthrough",
        type_pair=("STRING", "STRING"),
        template="def transform(v):\n    return v",
        applicable_blockers=(),
        historical_pass_rate=0.95,
    ),
    SketchHint(
        sketch_id="string_strip_normalize",
        type_pair=("STRING", "STRING"),
        template=(
            "def transform(v):\n"
            "    if v is None: return None\n"
            "    return v.strip()"
        ),
        applicable_blockers=("encoding_anomaly",),
        historical_pass_rate=0.88,
    ),
    SketchHint(
        sketch_id="email_lowercase_normalize",
        type_pair=("STRING", "STRING"),
        template=(
            "def transform(v):\n"
            "    if v is None: return None\n"
            "    return v.strip().lower()"
        ),
        applicable_blockers=("encoding_anomaly",),
        historical_pass_rate=0.90,
    ),
    SketchHint(
        sketch_id="sentinel_to_none",
        type_pair=("STRING", "STRING"),
        template=(
            "def transform(v):\n"
            "    SENTINELS = {'N/A', 'NULL', 'null', '<NULL>', '-1', '9999', 'TBD', 'unknown'}\n"
            "    if v is None or (isinstance(v, str) and v.strip() in SENTINELS):\n"
            "        return None\n"
            "    return v"
        ),
        applicable_blockers=("sentinel_value",),
        historical_pass_rate=0.82,
    ),
    SketchHint(
        sketch_id="date_to_timestamptz_utc_midnight",
        type_pair=("DATE", "TIMESTAMP_TZ"),
        template=(
            "def transform(v):\n"
            "    if v is None: return None\n"
            "    return datetime.datetime.combine(v, datetime.time.min, "
            "tzinfo=datetime.timezone.utc)"
        ),
        applicable_blockers=("timezone_drift",),
        historical_pass_rate=0.85,
    ),
    SketchHint(
        sketch_id="timestamp_to_timestamptz_utc",
        type_pair=("TIMESTAMP", "TIMESTAMP_TZ"),
        template=(
            "def transform(v):\n"
            "    if v is None: return None\n"
            "    return v.replace(tzinfo=datetime.timezone.utc)"
        ),
        applicable_blockers=("timezone_drift",),
        historical_pass_rate=0.80,
    ),
    SketchHint(
        sketch_id="decimal_precision_clamp_half_up",
        type_pair=("DECIMAL", "DECIMAL"),
        template=(
            "def transform(v):\n"
            "    if v is None: return None\n"
            "    d = decimal.Decimal(str(v))\n"
            "    q = decimal.Decimal('1E-2')\n"
            "    return d.quantize(q, rounding=decimal.ROUND_HALF_UP)"
        ),
        applicable_blockers=("precision_boundary",),
        historical_pass_rate=0.78,
    ),
    SketchHint(
        sketch_id="int_widening",
        type_pair=("INTEGER", "BIGINT"),
        template="def transform(v):\n    return v if v is None else int(v)",
        applicable_blockers=(),
        historical_pass_rate=0.93,
    ),
    SketchHint(
        sketch_id="int_narrowing_overflow_to_none",
        type_pair=("BIGINT", "INTEGER"),
        template=(
            "def transform(v):\n"
            "    if v is None: return None\n"
            "    return v if -(2**31) <= v < 2**31 else None"
        ),
        applicable_blockers=("precision_boundary",),
        historical_pass_rate=0.65,
    ),
    SketchHint(
        sketch_id="bool_from_int_or_text",
        type_pair=("INTEGER", "BOOLEAN"),
        template=(
            "def transform(v):\n"
            "    if v is None: return None\n"
            "    if isinstance(v, bool): return v\n"
            "    if isinstance(v, int): return v != 0\n"
            "    s = str(v).strip().lower()\n"
            "    return s in ('y', 't', 'true', '1', 'yes')"
        ),
        applicable_blockers=(),
        historical_pass_rate=0.86,
    ),
    SketchHint(
        sketch_id="json_text_to_object",
        type_pair=("STRING", "JSON"),
        template=(
            "def transform(v):\n"
            "    if v is None: return None\n"
            "    return json.loads(v) if isinstance(v, str) else v"
        ),
        applicable_blockers=(),
        historical_pass_rate=0.81,
    ),
    SketchHint(
        sketch_id="object_to_json_text",
        type_pair=("JSON", "STRING"),
        template=(
            "def transform(v):\n"
            "    if v is None: return None\n"
            "    return json.dumps(v)"
        ),
        applicable_blockers=(),
        historical_pass_rate=0.84,
    ),
    SketchHint(
        sketch_id="uuid_format_normalize_lower",
        type_pair=("STRING", "STRING"),
        template=(
            "def transform(v):\n"
            "    if v is None: return None\n"
            "    return v.strip().lower().replace('{', '').replace('}', '')"
        ),
        applicable_blockers=(),
        historical_pass_rate=0.79,
    ),
    SketchHint(
        sketch_id="phone_normalize_digits_only",
        type_pair=("STRING", "STRING"),
        template=(
            "def transform(v):\n"
            "    if v is None: return None\n"
            "    return re.sub(r'\\D+', '', v)"
        ),
        applicable_blockers=("encoding_anomaly",),
        historical_pass_rate=0.75,
    ),
    SketchHint(
        sketch_id="binary_hex_passthrough",
        type_pair=("BYTES", "BYTES"),
        template="def transform(v):\n    return v",
        applicable_blockers=(),
        historical_pass_rate=0.91,
    ),
)


def _normalized_pair(legacy: ColumnSpec | None, target: ColumnSpec | None) -> Tuple[str, str]:
    a = (legacy.normalized_type if legacy else "") or ""
    b = (target.normalized_type if target else "") or ""
    a = a.upper().split("(")[0]
    b = b.upper().split("(")[0]
    # collapse VARCHAR/TEXT/CHAR/CLOB → STRING for sketch matching
    a = "STRING" if a in ("STRING", "VARCHAR", "VARCHAR2", "TEXT", "CHAR", "CLOB") else a
    b = "STRING" if b in ("STRING", "VARCHAR", "VARCHAR2", "TEXT", "CHAR", "CLOB") else b
    return a, b


def select_sketches(
    mapping: ColumnMapping,
    legacy: ColumnSpec | None,
    target: ColumnSpec | None,
    blockers: Tuple[AnomalyFinding, ...],
    pruned_ids: Tuple[str, ...] = (),
    *,
    library: Tuple[SketchHint, ...] = SKETCHES,
    top_k: int = 3,
) -> Tuple[SketchHint, ...]:
    """Return up to ``top_k`` sketches matching the type pair + blocker
    categories, excluding any in ``pruned_ids``, sorted by
    ``historical_pass_rate`` descending."""
    type_pair = _normalized_pair(legacy, target)
    blocker_cats = frozenset(b.probe_category for b in blockers if b.severity == "blocker")
    candidates: list[Tuple[float, SketchHint]] = []
    for s in library:
        if s.sketch_id in pruned_ids:
            continue
        if s.type_pair != type_pair:
            continue
        # Score: base = historical_pass_rate; bonus if applicable_blockers overlap.
        overlap = blocker_cats.intersection(s.applicable_blockers)
        score = s.historical_pass_rate + 0.05 * len(overlap)
        candidates.append((score, s))
    candidates.sort(key=lambda kv: kv[0], reverse=True)
    return tuple(s for _, s in candidates[:top_k])


def run_with_cegis(
    *,
    mapping: ColumnMapping,
    legacy_column: ColumnSpec | None,
    target_column: ColumnSpec | None,
    property_set: PropertySet,
    blockers: Tuple[AnomalyFinding, ...] = (),
    sample_values: Tuple[str, ...] = (),
    max_iterations: int = 5,
    loop_walltime_sec: int = 1200,
) -> Union[ReflexionSuccess, ReflexionHalt]:
    """Run the Reflexion loop with CEGIS sketch hints. Returns the loop's
    terminal state. ``ReflexionSuccess.pruned_sketches`` records which sketch
    IDs were tried and failed during the run.
    """

    def _factory(pruned: Tuple[str, ...]) -> Tuple[SketchHint, ...]:
        return select_sketches(
            mapping,
            legacy_column,
            target_column,
            blockers,
            pruned_ids=pruned,
        )

    inputs = LoopInputs(
        mapping=mapping,
        legacy_column=legacy_column,
        target_column=target_column,
        property_set=property_set,
        blockers=blockers,
        sample_values=sample_values,
        sketch_hints_factory=_factory,
    )
    return run(inputs, max_iterations=max_iterations, loop_walltime_sec=loop_walltime_sec)


__all__ = ["SKETCHES", "select_sketches", "run_with_cegis"]
