"""Gate 5 — property-based Java equivalence.

Python owns Hypothesis case generation. The vendored JVM harness owns Java
compilation, classloader isolation, reflection invocation, and Java-accurate
return-value equality.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, Phase, find, given, settings
from hypothesis import strategies as st
from hypothesis.errors import FailedHealthCheck, NoSuchExample, Unsatisfiable

from omnix.gates.result import GateError
from omnix.semantic.node import SemanticNode

_GATE_NUMBER = 5
_GATE_NAME = "property_based"

HARNESS_JAR_PATH: Path = (
    Path(__file__).resolve().parent.parent
    / "semantic"
    / "java"
    / "vendor"
    / "java-equivalence-harness.jar"
)

_INT_MIN = -(2**31)
_INT_MAX = 2**31 - 1
_LONG_MIN = -(2**63)
_LONG_MAX = 2**63 - 1

JAVA_TYPE_STRATEGIES: dict[str, st.SearchStrategy[Any]] = {
    "byte": st.integers(min_value=-128, max_value=127),
    "short": st.integers(min_value=-(2**15), max_value=2**15 - 1),
    "int": st.integers(min_value=_INT_MIN, max_value=_INT_MAX),
    "java.lang.Integer": st.integers(min_value=_INT_MIN, max_value=_INT_MAX),
    "long": st.integers(min_value=_LONG_MIN, max_value=_LONG_MAX),
    "java.lang.Long": st.integers(min_value=_LONG_MIN, max_value=_LONG_MAX),
    "double": st.floats(allow_nan=False, allow_infinity=False, width=64),
    "java.lang.Double": st.floats(allow_nan=False, allow_infinity=False, width=64),
    "float": st.floats(allow_nan=False, allow_infinity=False, width=32),
    "java.lang.Float": st.floats(allow_nan=False, allow_infinity=False, width=32),
    "boolean": st.booleans(),
    "java.lang.Boolean": st.booleans(),
    "char": st.characters(),
    "java.lang.Character": st.characters(),
    "java.lang.String": st.text(max_size=200),
    "byte[]": st.binary(max_size=200).map(lambda b: list(b)),
    "int[]": st.lists(st.integers(min_value=_INT_MIN, max_value=_INT_MAX), max_size=50),
}

_BOUNDARY_VALUES: dict[str, tuple[Any, ...]] = {
    "byte": (-128, -1, 0, 1, 127),
    "short": (-(2**15), -1, 0, 1, 2**15 - 1),
    "int": (_INT_MIN, -1, 0, 1, _INT_MAX),
    "java.lang.Integer": (_INT_MIN, -1, 0, 1, _INT_MAX),
    "long": (_LONG_MIN, -1, 0, 1, _LONG_MAX),
    "java.lang.Long": (_LONG_MIN, -1, 0, 1, _LONG_MAX),
    "double": (-1.0, -0.0, 0.0, 1.0),
    "java.lang.Double": (-1.0, -0.0, 0.0, 1.0),
    "float": (-1.0, -0.0, 0.0, 1.0),
    "java.lang.Float": (-1.0, -0.0, 0.0, 1.0),
    "boolean": (False, True),
    "java.lang.Boolean": (False, True),
    "char": ("", "a", "Z"),
    "java.lang.Character": ("", "a", "Z"),
    "java.lang.String": ("", "a", "ab", " ", "hello"),
    "byte[]": ([], [0], [255], [0, 1, 255]),
    "int[]": ([], [0], [-1, 0, 1], [_INT_MIN, _INT_MAX]),
}


def check(
    legacy_source: str,
    rebuilt_source: str,
    semantic_node: SemanticNode,
) -> GateError | None:
    """Return None when generated Java cases show no behavioral divergence."""
    param_types = tuple(semantic_node.resolved_param_types)
    unsupported = [t for t in param_types if _strategy_for(t) is None]
    if unsupported:
        return _gate_error(
            "unsupported parameter type for gate 5",
            status="skipped",
            reason="unsupported_parameter_type",
            unsupported_types=unsupported,
        )

    max_examples = _max_examples()
    case_strategy = st.tuples(*(_strategy_for(t) for t in param_types))
    generated = _collect_cases(case_strategy, max_examples)
    if isinstance(generated, GateError):
        return generated

    cases = _boundary_cases(param_types)
    boundary_count = len(cases)
    remaining = max(0, max_examples - len(cases))
    cases.extend(generated[:remaining])
    if not cases and not param_types:
        cases.append(())

    payload = {
        "legacy_source": legacy_source,
        "rebuilt_source": rebuilt_source,
        "class_name": _class_name_from_fqn(semantic_node.fqn),
        "method_name": semantic_node.fqn.rsplit(".", 1)[-1],
        "parameter_types": list(param_types),
        "cases": [_json_safe_case(case) for case in cases[:max_examples]],
    }

    records_or_error = _run_harness(payload, timeout_s=_total_timeout_s())
    if isinstance(records_or_error, GateError):
        return records_or_error

    for record in records_or_error:
        if record.get("equivalent") is True:
            continue
        diverging_input = record.get("input", [])
        case_index = int(record.get("case_index", -1))
        shrunk = None
        if case_index >= boundary_count:
            shrunk = _shrink_divergence(
                case_strategy=case_strategy,
                payload=payload,
                original=tuple(diverging_input),
            )
        if shrunk is not None:
            diverging_input = list(shrunk)
            payload["cases"] = [_json_safe_case(tuple(shrunk))]
            rerun = _run_harness(payload, timeout_s=_case_timeout_s())
            if not isinstance(rerun, GateError) and rerun:
                record = rerun[0]
        legacy = record.get("legacy", {})
        rebuilt = record.get("rebuilt", {})
        return _gate_error(
            "property-based equivalence divergence",
            status="failed",
            reason="behavior_divergence",
            diverging_input=diverging_input,
            divergence=record.get("divergence"),
            legacy_return=legacy.get("return_value"),
            rebuilt_return=rebuilt.get("return_value"),
            legacy_exception=legacy.get("exception"),
            rebuilt_exception=rebuilt.get("exception"),
            examples_used=len(payload["cases"]),
        )

    return None


def _strategy_for(java_type: str) -> st.SearchStrategy[Any] | None:
    if java_type in JAVA_TYPE_STRATEGIES:
        return JAVA_TYPE_STRATEGIES[java_type]
    if java_type.startswith("java.util.List<") or java_type.startswith("java.util.Set<"):
        inner = java_type[java_type.index("<") + 1 : -1]
        inner_strategy = _strategy_for(inner)
        if inner_strategy is None:
            return None
        return st.lists(inner_strategy, max_size=50)
    return None


def _collect_cases(
    case_strategy: st.SearchStrategy[tuple[Any, ...]],
    max_examples: int,
) -> list[tuple[Any, ...]] | GateError:
    examples: list[tuple[Any, ...]] = []

    @settings(
        max_examples=max_examples,
        database=None,
        deadline=None,
        phases=(Phase.generate,),
        suppress_health_check=(HealthCheck.too_slow,),
        derandomize=True,
    )
    @given(case_strategy)
    def _collect(case: tuple[Any, ...]) -> None:
        examples.append(case)

    try:
        _collect()
    except (FailedHealthCheck, Unsatisfiable) as exc:
        return _gate_error(
            "hypothesis could not generate enough usable gate 5 examples",
            status="inconclusive",
            reason="high_assume_rejection_rate",
            examples_tried=max_examples,
            examples_used=len(examples),
            exception=type(exc).__name__,
        )
    return examples


def _shrink_divergence(
    *,
    case_strategy: st.SearchStrategy[tuple[Any, ...]],
    payload: dict[str, Any],
    original: tuple[Any, ...],
) -> tuple[Any, ...] | None:
    def _is_divergent(case: tuple[Any, ...]) -> bool:
        probe = dict(payload)
        probe["cases"] = [_json_safe_case(case)]
        records = _run_harness(probe, timeout_s=_case_timeout_s())
        return not isinstance(records, GateError) and bool(records) and records[0].get("equivalent") is not True

    try:
        return find(
            case_strategy,
            _is_divergent,
            settings=settings(
                max_examples=max(25, _max_examples()),
                database=None,
                deadline=None,
                derandomize=True,
                suppress_health_check=(HealthCheck.too_slow,),
            ),
        )
    except (NoSuchExample, FailedHealthCheck, Unsatisfiable):
        return original


def _run_harness(payload: dict[str, Any], *, timeout_s: float) -> list[dict[str, Any]] | GateError:
    if not HARNESS_JAR_PATH.exists():
        return _gate_error(
            "gate 5 JVM harness jar missing",
            status="runtime_crash",
            reason="harness_jar_missing",
            jar_path=str(HARNESS_JAR_PATH),
        )
    try:
        proc = subprocess.run(
            ["java", "-jar", str(HARNESS_JAR_PATH)],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return _gate_error(
            "gate 5 JVM harness timed out",
            status="runtime_crash",
            reason="harness_timeout",
            timeout_s=timeout_s,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
        )
    except OSError as exc:
        return _gate_error(
            "gate 5 JVM harness could not start",
            status="runtime_crash",
            reason="harness_start_failed",
            exception=type(exc).__name__,
            error_message=str(exc),
        )

    if proc.returncode != 0:
        return _gate_error(
            "gate 5 JVM harness exited non-zero",
            status="runtime_crash",
            reason="harness_exit",
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    records: list[dict[str, Any]] = []
    end_seen = False
    try:
        # The harness emits one JSON object per LF. Do not use splitlines():
        # Hypothesis can generate Java strings containing Unicode line
        # separators that Python treats as line breaks but JSON does not.
        for line in proc.stdout.split("\n"):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("__END__") is True:
                end_seen = True
                continue
            records.append(obj)
    except (json.JSONDecodeError, TypeError) as exc:
        return _gate_error(
            "gate 5 JVM harness emitted malformed JSON",
            status="runtime_crash",
            reason="malformed_harness_output",
            exception=type(exc).__name__,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    if not end_seen:
        return _gate_error(
            "gate 5 JVM harness did not emit end sentinel",
            status="runtime_crash",
            reason="missing_end_sentinel",
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    return records


def _boundary_cases(param_types: tuple[str, ...]) -> list[tuple[Any, ...]]:
    if not param_types:
        return [()]
    if len(param_types) == 1:
        return [(value,) for value in _BOUNDARY_VALUES.get(param_types[0], ())]
    out: list[tuple[Any, ...]] = []
    defaults = tuple(_BOUNDARY_VALUES.get(t, (None,))[0] for t in param_types)
    for index, java_type in enumerate(param_types):
        for value in _BOUNDARY_VALUES.get(java_type, ())[:3]:
            case = list(defaults)
            case[index] = value
            out.append(tuple(case))
    return out


def _json_safe_case(case: tuple[Any, ...]) -> list[Any]:
    return [_json_safe_value(value) for value in case]


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return list(value)
    if isinstance(value, tuple):
        return [_json_safe_value(v) for v in value]
    if isinstance(value, list):
        return [_json_safe_value(v) for v in value]
    if isinstance(value, set):
        return [_json_safe_value(v) for v in sorted(value, key=repr)]
    return value


def _class_name_from_fqn(fqn: str) -> str:
    owner, _, _method = fqn.rpartition(".")
    return owner


def _max_examples() -> int:
    raw = os.environ.get("OMNIX_GATE5_MAX_EXAMPLES", "200")
    try:
        value = int(raw)
    except ValueError:
        value = 200
    return max(1, value)


def _case_timeout_s() -> float:
    raw = os.environ.get("OMNIX_GATE5_CASE_TIMEOUT_S", "30")
    try:
        return max(0.1, float(raw))
    except ValueError:
        return 30.0


def _total_timeout_s() -> float:
    raw = os.environ.get("OMNIX_GATE5_TOTAL_TIMEOUT_S", "300")
    try:
        return max(0.1, float(raw))
    except ValueError:
        return 300.0


def _gate_error(message: str, **details: Any) -> GateError:
    return GateError(
        gate_number=_GATE_NUMBER,
        gate_name=_GATE_NAME,
        message=message,
        details=details,
    )
