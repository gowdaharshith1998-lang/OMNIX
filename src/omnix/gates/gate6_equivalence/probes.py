"""Probe generation for Gate 6 behavioral equivalence."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

from hypothesis import HealthCheck, Phase, given, settings
from hypothesis import strategies as st
from hypothesis.errors import FailedHealthCheck, Unsatisfiable

from omnix.gates import gate5_property
from omnix.gates.result import GateError
from omnix.semantic.node import SemanticNode

ProbeInput: TypeAlias = list[Any]

DEFAULT_CONSTRUCT_MARKER = "__omnix_default_construct__"
FLOAT_MARKER = "__omnix_float__"
MAX_PROBES_PER_METHOD = 200

_DOUBLE_MIN_VALUE = float.fromhex("0x0.0000000000001p-1022")
_FLOAT_MIN_VALUE = 1.401298464324817e-45
_FLOAT_MAX_VALUE = 3.4028234663852886e38


@dataclass(frozen=True)
class ProbeSet:
    """Generated Gate 6 probes plus receipt-ready generation details."""

    probes: list[ProbeInput]
    details: dict[str, Any]


def generate_probes(
    semantic_node: SemanticNode,
    *,
    num_random: int = 100,
    gate5_error: GateError | None = None,
    gate5_details: Mapping[str, Any] | None = None,
) -> list[ProbeInput]:
    """Return concrete probe inputs for Gate 6."""
    return generate_probe_set(
        semantic_node,
        num_random=num_random,
        gate5_error=gate5_error,
        gate5_details=gate5_details,
    ).probes


def generate_probe_set(
    semantic_node: SemanticNode,
    *,
    num_random: int = 100,
    gate5_error: GateError | None = None,
    gate5_details: Mapping[str, Any] | None = None,
) -> ProbeSet:
    """Generate boundary, random, and Gate-5-derived probes."""
    param_types = tuple(semantic_node.resolved_param_types)
    partial_types = [t for t in param_types if _strategy_for(t) is None]
    boundary_probes = _boundary_probes(param_types)
    injected_probes = _injected_probes(gate5_error=gate5_error, gate5_details=gate5_details)

    random_budget = max(0, MAX_PROBES_PER_METHOD - len(boundary_probes) - len(injected_probes))
    requested_random = max(0, num_random)
    random_limit = min(requested_random, random_budget)
    random_probes = [] if partial_types else _random_probes(param_types, random_limit)

    probes = (boundary_probes + random_probes + injected_probes)[:MAX_PROBES_PER_METHOD]
    details = {
        "boundary_count": len(boundary_probes),
        "random_count": len(random_probes),
        "injected_count": len(injected_probes),
        "probe_count": len(probes),
        "requested_random_count": requested_random,
        "max_probes": MAX_PROBES_PER_METHOD,
        "partial": bool(partial_types),
        "partial_types": partial_types,
    }
    if partial_types:
        details["reason"] = "unsupported_parameter_type_partial_probe_set"
    return ProbeSet(probes=probes, details=details)


def _strategy_for(java_type: str) -> st.SearchStrategy[Any] | None:
    if java_type in gate5_property.JAVA_TYPE_STRATEGIES:
        return gate5_property.JAVA_TYPE_STRATEGIES[java_type]
    if java_type.startswith("java.util.List<") or java_type.startswith("java.util.Set<"):
        inner = java_type[java_type.index("<") + 1 : -1]
        inner_strategy = _strategy_for(inner)
        if inner_strategy is None:
            return None
        return st.lists(inner_strategy, max_size=50)
    return None


def _boundary_probes(param_types: tuple[str, ...]) -> list[ProbeInput]:
    if not param_types:
        return [[]]
    if len(param_types) == 1:
        return [[value] for value in _boundary_values(param_types[0])]

    defaults = [_default_value(java_type) for java_type in param_types]
    probes: list[ProbeInput] = []
    for index, java_type in enumerate(param_types):
        for value in _boundary_values(java_type):
            probe = list(defaults)
            probe[index] = value
            probes.append(probe)
    return probes


def _boundary_values(java_type: str) -> tuple[Any, ...]:
    if java_type == "java.lang.String":
        return (None, "", " ", "a", "A" * 1000, "\U0001f984")
    if java_type in {"int", "java.lang.Integer"}:
        return (-(2**31), -1, 0, 1, 2**31 - 1)
    if java_type in {"long", "java.lang.Long"}:
        return (-(2**63), -1, 0, 1, 2**63 - 1)
    if java_type in {"double", "java.lang.Double"}:
        return (
            {FLOAT_MARKER: "NaN"},
            {FLOAT_MARKER: "+Infinity"},
            {FLOAT_MARKER: "-Infinity"},
            0.0,
            -0.0,
            _DOUBLE_MIN_VALUE,
            sys.float_info.max,
        )
    if java_type in {"float", "java.lang.Float"}:
        return (
            {FLOAT_MARKER: "NaN"},
            {FLOAT_MARKER: "+Infinity"},
            {FLOAT_MARKER: "-Infinity"},
            0.0,
            -0.0,
            _FLOAT_MIN_VALUE,
            _FLOAT_MAX_VALUE,
        )
    if java_type in {"boolean", "java.lang.Boolean"}:
        return (False, True)
    if java_type in {"char", "java.lang.Character"}:
        return ("a", "Z", "\0")
    if java_type == "byte[]":
        return ([], [0], [255], [0, 1, 255])
    if java_type == "int[]":
        return ([], [0], [-1, 0, 1], [-(2**31), 2**31 - 1])
    return (None, {DEFAULT_CONSTRUCT_MARKER: java_type})


def _default_value(java_type: str) -> Any:
    return _boundary_values(java_type)[0]


def _random_probes(param_types: tuple[str, ...], count: int) -> list[ProbeInput]:
    if count <= 0:
        return []
    strategies = tuple(_strategy_for(t) for t in param_types)
    if any(strategy is None for strategy in strategies):
        return []
    case_strategy = st.tuples(*(strategy for strategy in strategies if strategy is not None))
    examples: list[ProbeInput] = []

    @settings(
        max_examples=count,
        database=None,
        deadline=None,
        phases=(Phase.generate,),
        suppress_health_check=(HealthCheck.too_slow,),
        derandomize=True,
    )
    @given(case_strategy)
    def _collect(case: tuple[Any, ...]) -> None:
        examples.append([_json_safe_value(value) for value in case])

    try:
        _collect()
    except (FailedHealthCheck, Unsatisfiable):
        return examples
    return examples[:count]


def _injected_probes(
    *,
    gate5_error: GateError | None,
    gate5_details: Mapping[str, Any] | None,
) -> list[ProbeInput]:
    details = gate5_details
    if gate5_error is not None:
        details = gate5_error.details
    if not details or details.get("status") != "failed":
        return []
    if "diverging_input" not in details:
        return []
    raw = details["diverging_input"]
    if isinstance(raw, list):
        return [[_json_safe_value(value) for value in raw]]
    if isinstance(raw, tuple):
        return [[_json_safe_value(value) for value in raw]]
    return [[_json_safe_value(raw)]]


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
