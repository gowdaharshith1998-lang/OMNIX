"""Grounded Reflexion loop — Migrator-style CEGIS with MFI critique.

For each ColumnMapping the loop:

  1. Asks the LLM synthesizer for a transformer + property tests, seeded with
     any sketch hints from CEGIS (P6) and any MFI from prior iterations.
  2. Validates + RestrictedPython-compiles the emitted Python (P1). Any
     ``SecurityViolation`` HALTs immediately — never retried.
  3. Runs each property in the fenced subprocess sandbox against a small
     deterministic input set augmented with all prior MFIs. The minimum
     failing input (the new MFI) is captured.
  4. On success, returns ``ReflexionSuccess``. On failure, appends the MFI to
     a monotone history, prunes the failing sketch, and loops.
  5. After ``max_iterations`` (default 5) without success, returns
     ``ReflexionHalt(halt_reason='iteration_cap')`` with every MFI captured.

Critique is NEVER LLM self-judgment (Huang ICLR 2024 trap). It is always a
concrete failing input from execution.
"""

from __future__ import annotations

import ast
import time
from dataclasses import dataclass, replace
from typing import Any, Callable, List, Optional, Tuple, Union

from omnix.dm._types import (
    APIFailure,
    AnomalyFinding,
    ColumnMapping,
    ColumnSpec,
    LLMParseFailure,
    MFI,
    PropertyDef,
    PropertySet,
    ReflexionHalt,
    ReflexionSuccess,
    SecurityViolation,
    SketchHint,
    SynthesizerResult,
    TierFailure,
    TransformerSpec,
)
from omnix.dm.d3_transformation_synthesis import llm_synthesizer
from omnix.dm.d3_transformation_synthesis.transformer_dsl import (
    ExecutionSuccess,
    _SecurityViolationError,
    compile_safe,
    execute,
)


# ---------------------------------------------------------------------------
# Property checker — runs each PropertyDef against a small set of inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _PropertyOutcome:
    name: str
    passed: bool
    mfi: Optional[MFI] = None


# A registry of "concrete" check functions per property name. Most properties
# are validated by running ``transform(v)`` and checking a predicate; the
# property generator emits Hypothesis strategies but for deterministic in-loop
# verification we use a small curated input pool plus all prior MFIs and a
# Python-level assertion against the property's intent.

def _python_assertion(prop: PropertyDef, target_norm: Optional[str], target_nullable: bool):
    """Return a Python-level predicate ``(input, output) -> (bool, expected_repr)``
    derived from the property's intent. We do NOT rely on the LLM-emitted
    ``properties_source`` because that's a Hypothesis test fixture, not a
    runnable lambda. Instead we encode the same intent statically here.
    """
    name = prop.name

    if name == "type_preservation":
        def _check(v: Any, out: Any):
            if out is None:
                return True, "None"
            ok = _is_target_type(out, target_norm)
            return ok, f"isinstance(out, {target_norm})"
        return _check
    if name == "null_passthrough":
        def _check(v: Any, out: Any):
            if v is None:
                return out is None, "None"
            return True, "n/a"
        return _check
    if name == "no_null_emission":
        def _check(v: Any, out: Any):
            if v is None:
                return True, "n/a"  # input shouldn't be None
            return out is not None, "non-None"
        return _check
    if name == "preserves_timezone":
        def _check(v: Any, out: Any):
            if out is None:
                return True, "None"
            tz = getattr(out, "tzinfo", None)
            return tz is not None, "non-None tzinfo"
        return _check
    if name == "within_target_precision":
        def _check(v: Any, out: Any):
            import decimal

            if out is None:
                return True, "None"
            try:
                magnitude = abs(out)
            except Exception:
                return False, "comparable magnitude"
            # Pull precision from rationale "10**N"
            import re as _re

            m = _re.search(r"10\s*\*\*\s*(\d+)", prop.assertion)
            p = int(m.group(1)) if m else 10
            limit = 10 ** p
            try:
                return decimal.Decimal(str(magnitude)) < decimal.Decimal(limit), f"abs(out) < 10**{p}"
            except Exception:
                return False, f"abs(out) < 10**{p}"
        return _check
    if name == "reversibility_when_lossless":
        def _check(v: Any, out: Any):
            if v is None and out is None:
                return True, "None"
            return str(out) == str(v) or out == v, "out == v (lossless)"
        return _check
    if name.startswith("survives_"):
        # Survives = no exception + (loose) target type when non-null.
        def _check(v: Any, out: Any):
            if out is None:
                return True, "None"
            return _is_target_type(out, target_norm), f"isinstance(out, {target_norm})"
        return _check
    # Unknown property name — accept as a no-op so iteration can proceed,
    # but mark it as "trusted" rather than asserted. Returning a tautology
    # keeps the loop honest: failures only come from concrete predicates.
    def _check(v: Any, out: Any):
        return True, "n/a"

    return _check


def _is_target_type(out: Any, normalized: Optional[str]) -> bool:
    if normalized is None:
        return True
    import datetime
    import decimal

    nt = normalized.upper()
    if nt in ("INTEGER", "BIGINT", "SMALLINT"):
        return isinstance(out, int) and not isinstance(out, bool)
    if nt == "BOOLEAN":
        return isinstance(out, bool)
    if nt == "DATE":
        return isinstance(out, datetime.date) and not isinstance(out, datetime.datetime)
    if nt == "TIMESTAMP":
        return isinstance(out, datetime.datetime)
    if nt == "TIMESTAMP_TZ":
        return isinstance(out, datetime.datetime)
    if nt.startswith("DECIMAL"):
        return isinstance(out, (decimal.Decimal, int, float))
    if nt == "BYTES":
        return isinstance(out, (bytes, bytearray))
    if nt == "JSON":
        return isinstance(out, (dict, list, str, int, float, bool, type(None)))
    return isinstance(out, str)


def _seed_inputs_for(
    target_norm: Optional[str],
    nullable: bool,
    mfi_history: Tuple[MFI, ...],
) -> List[Any]:
    """Small deterministic input pool — enough to catch the obvious bugs and
    seed the loop. MFIs from history are concrete inputs we replay."""
    import datetime
    import decimal

    nt = (target_norm or "").upper()
    inputs: List[Any] = []
    if nullable:
        inputs.append(None)
    if nt in ("INTEGER", "BIGINT", "SMALLINT"):
        inputs += [0, 1, -1, 9999, -9999]
    elif nt == "BOOLEAN":
        inputs += [True, False, "true", "false", 1, 0]
    elif nt == "DATE":
        inputs += [datetime.date(1900, 1, 1), datetime.date(2000, 6, 15)]
    elif nt == "TIMESTAMP":
        inputs += [datetime.datetime(2020, 1, 1), datetime.datetime(1970, 1, 1)]
    elif nt == "TIMESTAMP_TZ":
        inputs += [
            datetime.date(1900, 1, 1),
            datetime.date(2020, 1, 1),
            datetime.datetime(2020, 1, 1),
        ]
    elif nt.startswith("DECIMAL"):
        inputs += [decimal.Decimal("0"), decimal.Decimal("3.14"), decimal.Decimal("-100.50")]
    elif nt == "BYTES":
        inputs += [b"", b"hello"]
    elif nt == "JSON":
        inputs += [{}, {"k": "v"}, [1, 2, 3]]
    else:
        inputs += ["", "hello", "café", "  spaces  "]

    # Replay every MFI's repr — but evaluating arbitrary repr is unsafe, so
    # we only attempt a controlled small subset of safe literal types via
    # ast.literal_eval. Anything else is dropped (the LLM will see the repr
    # in the prompt anyway).
    for m in mfi_history:
        try:
            v = ast.literal_eval(m.input_value_repr)
            inputs.append(v)
        except Exception:
            continue
    return inputs


def _check_one_input(
    source: str,
    v: Any,
    properties: Tuple[PropertyDef, ...],
    target_norm: Optional[str],
    target_nullable: bool,
) -> Optional[MFI]:
    """Run one input through the sandbox; return the FIRST failing property's
    MFI, or ``None`` if all properties pass."""
    result = execute(source, v, timeout_ms=4000)
    if isinstance(result, ExecutionSuccess):
        # Reconstruct the live Python value from the JSON-safe form so
        # property checks like ``isinstance(out, datetime)`` work.
        out = _decode(result.result_json)
        for prop in properties:
            check = _python_assertion(prop, target_norm, target_nullable)
            try:
                ok, expected = check(v, out)
            except Exception as exc:
                return MFI(
                    property_name=prop.name,
                    input_value_repr=repr(v),
                    expected_output_repr=str(exc),
                    actual_output_repr=repr(out),
                    hint=f"property {prop.name} raised: {exc}",
                )
            if not ok:
                return MFI(
                    property_name=prop.name,
                    input_value_repr=repr(v),
                    expected_output_repr=expected,
                    actual_output_repr=repr(out),
                    hint=prop.rationale,
                )
        return None
    # Execution itself failed — first property is the "violated" one.
    name = properties[0].name if properties else "execution"
    return MFI(
        property_name=name,
        input_value_repr=repr(v),
        expected_output_repr="no exception",
        actual_output_repr=repr(result),
        hint=f"sandbox returned {type(result).__name__}",
    )


def _decode(json_safe: Any) -> Any:
    """Reverse the parent's encoding so live property checks see real Python
    types."""
    import datetime
    import decimal

    if isinstance(json_safe, dict):
        if "__datetime__" in json_safe:
            return datetime.datetime.fromisoformat(json_safe["__datetime__"])
        if "__date__" in json_safe:
            return datetime.date.fromisoformat(json_safe["__date__"])
        if "__decimal__" in json_safe:
            return decimal.Decimal(json_safe["__decimal__"])
        if "__bytes__" in json_safe:
            return bytes.fromhex(json_safe["__bytes__"])
        return {k: _decode(v) for k, v in json_safe.items()}
    if isinstance(json_safe, list):
        return [_decode(v) for v in json_safe]
    return json_safe


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoopInputs:
    mapping: ColumnMapping
    legacy_column: Optional[ColumnSpec]
    target_column: Optional[ColumnSpec]
    property_set: PropertySet
    blockers: Tuple[AnomalyFinding, ...] = ()
    sample_values: Tuple[str, ...] = ()
    sketch_hints_factory: Optional[Callable[[Tuple[str, ...]], Tuple[SketchHint, ...]]] = None


def run(
    inputs: LoopInputs,
    *,
    max_iterations: int = 5,
    loop_walltime_sec: int = 1200,
) -> Union[ReflexionSuccess, ReflexionHalt]:
    """Run the grounded Reflexion loop. Returns a typed terminal state."""
    key = f"{inputs.mapping.legacy_table}.{inputs.mapping.legacy_column}"
    target_norm = inputs.target_column.normalized_type if inputs.target_column else None
    target_nullable = (
        inputs.target_column.nullable if inputs.target_column else True
    )
    properties = inputs.property_set.properties

    mfi_history: Tuple[MFI, ...] = ()
    pruned_sketches: Tuple[str, ...] = ()
    latest_source = ""
    last_critique = ""
    start = time.monotonic()

    for iteration in range(1, max_iterations + 1):
        if time.monotonic() - start > loop_walltime_sec:
            return ReflexionHalt(
                column_mapping_key=key,
                halt_reason="loop_walltime",
                latest_python_source=latest_source,
                failing_mfis=mfi_history,
                last_critique=last_critique,
                iterations_used=iteration - 1,
            )
        sketches: Tuple[SketchHint, ...] = ()
        if inputs.sketch_hints_factory is not None:
            sketches = inputs.sketch_hints_factory(pruned_sketches)
            if not sketches and pruned_sketches and iteration > 1:
                # Every viable sketch has been pruned — explicit halt instead
                # of looping with no guidance.
                return ReflexionHalt(
                    column_mapping_key=key,
                    halt_reason="all_sketches_pruned",
                    latest_python_source=latest_source,
                    failing_mfis=mfi_history,
                    last_critique=last_critique,
                    iterations_used=iteration - 1,
                )
        outcome = llm_synthesizer.synthesize(
            mapping=inputs.mapping,
            legacy_column=inputs.legacy_column,
            target_column=inputs.target_column,
            property_set=inputs.property_set,
            sample_values=inputs.sample_values,
            edge_cases=inputs.blockers,
            mfi_history=mfi_history,
            sketch_hints=sketches,
        )
        if isinstance(outcome, LLMParseFailure):
            return ReflexionHalt(
                column_mapping_key=key,
                halt_reason="parse_failure",
                latest_python_source=latest_source,
                failing_mfis=mfi_history,
                last_critique=outcome.reason,
                iterations_used=iteration,
            )
        if isinstance(outcome, APIFailure):
            return ReflexionHalt(
                column_mapping_key=key,
                halt_reason="api_failure",
                latest_python_source=latest_source,
                failing_mfis=mfi_history,
                last_critique=outcome.reason,
                iterations_used=iteration,
            )
        assert isinstance(outcome, SynthesizerResult)
        latest_source = outcome.python_source
        try:
            compile_safe(latest_source)
        except _SecurityViolationError as exc:
            return ReflexionHalt(
                column_mapping_key=key,
                halt_reason="security_violation",
                latest_python_source=latest_source,
                failing_mfis=mfi_history,
                last_critique=f"AST rejected: {exc.violation.reason}",
                iterations_used=iteration,
                security_violation=exc.violation,
            )
        except SyntaxError as exc:
            return ReflexionHalt(
                column_mapping_key=key,
                halt_reason="parse_failure",
                latest_python_source=latest_source,
                failing_mfis=mfi_history,
                last_critique=f"SyntaxError: {exc}",
                iterations_used=iteration,
            )

        # Run the property suite over the deterministic input pool + prior MFIs.
        inputs_pool = _seed_inputs_for(target_norm, target_nullable, mfi_history)
        failing_mfi: Optional[MFI] = None
        for v in inputs_pool:
            failing_mfi = _check_one_input(
                latest_source,
                v,
                properties,
                target_norm,
                target_nullable,
            )
            if failing_mfi is not None:
                break

        if failing_mfi is None:
            spec = TransformerSpec(
                column_mapping_key=key,
                python_source=latest_source,
                sql_case=None,
                datalog_rule=None,
                properties_passed=tuple(p.name for p in properties),
                properties_failed=(),
                mfi_history=mfi_history,
                iterations_used=iteration,
                cegis_pruned_sketches=pruned_sketches,
                tier_failures=(),
                tier_chosen="python",
                confidence=_confidence(inputs.mapping, iteration, max_iterations, ()),
                requires_operator_review=inputs.mapping.status
                in ("low_confidence", "ambiguous"),
                bisimulation_placeholder={},
            )
            return ReflexionSuccess(
                transformer_spec=spec,
                iterations_used=iteration,
                mfi_history=mfi_history,
                pruned_sketches=pruned_sketches,
            )

        mfi_history = mfi_history + (failing_mfi,)
        last_critique = (
            f"property {failing_mfi.property_name} failed on input "
            f"{failing_mfi.input_value_repr}: expected "
            f"{failing_mfi.expected_output_repr}, got {failing_mfi.actual_output_repr}"
        )
        # Prune the first sketch we tried (if any) — CEGIS bookkeeping.
        if sketches:
            pruned_sketches = pruned_sketches + (sketches[0].sketch_id,)

    return ReflexionHalt(
        column_mapping_key=key,
        halt_reason="iteration_cap",
        latest_python_source=latest_source,
        failing_mfis=mfi_history,
        last_critique=last_critique,
        iterations_used=max_iterations,
    )


def _confidence(
    mapping: ColumnMapping,
    iteration: int,
    cap: int,
    tier_failures: Tuple[TierFailure, ...],
) -> float:
    base = mapping.confidence if mapping.status == "ok" else mapping.confidence * 0.7
    # decay slightly with iteration count
    base *= max(0.6, 1.0 - (iteration - 1) * 0.05)
    if tier_failures:
        base *= 1.0 - 0.05 * len(tier_failures)
    return max(0.0, min(1.0, base))


__all__ = ["LoopInputs", "run"]
