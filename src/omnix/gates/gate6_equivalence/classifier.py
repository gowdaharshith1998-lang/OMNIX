"""Gate 6 behavioral-equivalence classifier."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from omnix.gates.gate6_equivalence.harness import ProbeResult, run_harness
from omnix.gates.gate6_equivalence.probes import ProbeSet, generate_probe_set
from omnix.gates.result import GateError
from omnix.semantic.node import SemanticNode, SourceLocation

Classification = Literal[
    "equivalent",
    "value_diverge",
    "exception_diverge",
    "stdout_diverge_deterministic",
    "stdout_diverge_stochastic",
    "wall_clock_diverge",
    "fp_tolerance_diverge",
]
Gate6Status = Literal["passed", "failed", "runtime_crash", "skipped", "inconclusive"]
LegacyReplay = Callable[[ProbeResult], Sequence[ProbeResult]]

_GATE_NUMBER = 6
_GATE_NAME = "behavioral_equivalence"
_DIVERGENCE_CLASSES = {
    "value_diverge",
    "exception_diverge",
    "stdout_diverge_deterministic",
}
_ACCEPTED_WITH_NOTE_CLASSES = {
    "stdout_diverge_stochastic",
    "wall_clock_diverge",
    "fp_tolerance_diverge",
}
_WALL_BUCKETS = {
    "<1ms": 0,
    "<10ms": 1,
    "<100ms": 2,
    "<1s": 3,
    "<10s": 4,
    ">10s": 5,
}
_DOUBLE_EPS = 2**-52


@dataclass(frozen=True)
class ClassifiedProbe:
    """A single probe with its Gate 6 classification."""

    result: ProbeResult
    classification: Classification


@dataclass(frozen=True)
class Gate6Evaluation:
    """Detailed Gate 6 result for receipt wiring."""

    status: Gate6Status
    details: dict[str, Any]
    error: GateError | None = None
    classified: tuple[ClassifiedProbe, ...] = ()
    probe_set: ProbeSet | None = None


def classify_results(
    probe_results: Sequence[ProbeResult],
    *,
    legacy_replay: LegacyReplay | None = None,
) -> list[ClassifiedProbe]:
    """Classify every probe result into exactly one Gate 6 bucket."""
    return [
        ClassifiedProbe(result=result, classification=_classify_one(result, legacy_replay))
        for result in probe_results
    ]


def evaluate_results(
    probe_results: Sequence[ProbeResult],
    *,
    legacy_replay: LegacyReplay | None = None,
    probe_set: ProbeSet | None = None,
) -> Gate6Evaluation:
    """Return the overall Gate 6 status for already-collected probe results."""
    classified = tuple(classify_results(probe_results, legacy_replay=legacy_replay))
    divergence = [c for c in classified if c.classification in _DIVERGENCE_CLASSES]
    accepted = [c for c in classified if c.classification in _ACCEPTED_WITH_NOTE_CLASSES]
    details: dict[str, Any] = {
        "status": "passed",
        "probe_count": len(classified),
        "divergence_count": len(divergence),
        "accepted_with_note_count": len(accepted),
        "classifications": [_classification_detail(c) for c in classified],
    }
    if probe_set is not None:
        details["probe_generation"] = dict(probe_set.details)

    if divergence:
        first = divergence[0]
        details.update(
            {
                "status": "failed",
                "classification": first.classification,
                "diverging_input": first.result.input,
            }
        )
        err = _gate_error("behavioral equivalence divergence", **details)
        return Gate6Evaluation(
            status="failed",
            details=details,
            error=err,
            classified=classified,
            probe_set=probe_set,
        )

    if len(classified) < 20:
        details.update({"status": "inconclusive", "reason": "insufficient_probe_count"})
        err = _gate_error("gate 6 needs at least 20 probes", **details)
        return Gate6Evaluation(
            status="inconclusive",
            details=details,
            error=err,
            classified=classified,
            probe_set=probe_set,
        )

    return Gate6Evaluation(
        status="passed",
        details=details,
        classified=classified,
        probe_set=probe_set,
    )


def evaluate(
    legacy_source: str,
    rebuilt_source: str,
    semantic_node: SemanticNode,
    *,
    gate5_details: Mapping[str, Any] | None = None,
    num_random: int | None = None,
    timeout_s: float = 60.0,
) -> Gate6Evaluation:
    """Generate probes, run the harness, classify results, and return receipt details."""
    try:
        random_count = _random_probe_count() if num_random is None else num_random
        probe_set = generate_probe_set(
            semantic_node,
            num_random=random_count,
            gate5_details=gate5_details,
        )
        class_name = _class_name_from_fqn(semantic_node.fqn)
        method_name = semantic_node.fqn.rsplit(".", 1)[-1]
        parameter_types = list(semantic_node.resolved_param_types)
        results = run_harness(
            legacy_source,
            rebuilt_source,
            class_name,
            method_name,
            probe_set.probes,
            parameter_types=parameter_types,
            timeout_s=timeout_s,
        )

        def _replay(result: ProbeResult) -> Sequence[ProbeResult]:
            return run_harness(
                legacy_source,
                legacy_source,
                class_name,
                method_name,
                [result.input, result.input, result.input],
                parameter_types=parameter_types,
                timeout_s=timeout_s,
            )

        return evaluate_results(results, legacy_replay=_replay, probe_set=probe_set)
    except Exception as exc:
        err = _gate_error(
            "gate 6 internal exception",
            status="failed",
            reason="gate6_internal_exception",
            exception=type(exc).__name__,
            error_message=str(exc),
        )
        return Gate6Evaluation(status="failed", details=dict(err.details), error=err)


def check(
    legacy_source: str,
    rebuilt_source: str,
    semantic_node: SemanticNode | None = None,
    *,
    class_name: str | None = None,
    method_name: str | None = None,
    parameter_types: Sequence[str] | None = None,
    gate5_details: Mapping[str, Any] | None = None,
    num_random: int | None = None,
    timeout_s: float = 60.0,
) -> GateError | None:
    """Return None when Gate 6 finds no blocking behavioral divergence."""
    node = semantic_node
    if node is None:
        if class_name is None or method_name is None:
            raise ValueError("semantic_node or class_name/method_name is required")
        node = SemanticNode(
            fqn=f"{class_name}.{method_name}",
            kind="method",
            signature="",
            resolved_param_types=tuple(parameter_types or ("java.lang.String",)),
            resolved_return_type=None,
            dependency_edges=(),
            source_location=SourceLocation(file_path=f"{class_name}.java", line=1),
        )
    return evaluate(
        legacy_source,
        rebuilt_source,
        node,
        gate5_details=gate5_details,
        num_random=num_random,
        timeout_s=timeout_s,
    ).error


def _classify_one(
    result: ProbeResult,
    legacy_replay: LegacyReplay | None,
) -> Classification:
    if _exceptions_differ(result):
        return "exception_diverge"
    if not _values_equal(result.return_value_legacy, result.return_value_rebuilt):
        if _within_fp_tolerance(result.return_value_legacy, result.return_value_rebuilt):
            return "fp_tolerance_diverge"
        if _legacy_return_is_stochastic(result, legacy_replay):
            return "stdout_diverge_stochastic"
        return "value_diverge"
    if (
        result.stdout_legacy_sha256 != result.stdout_rebuilt_sha256
        or result.stderr_legacy_sha256 != result.stderr_rebuilt_sha256
    ):
        if _legacy_stdout_is_stochastic(result, legacy_replay):
            return "stdout_diverge_stochastic"
        return "stdout_diverge_deterministic"
    if _wall_clock_distance(result) > 1:
        return "wall_clock_diverge"
    return "equivalent"


def _exceptions_differ(result: ProbeResult) -> bool:
    return (
        result.legacy_outcome != result.rebuilt_outcome
        or result.exception_legacy != result.exception_rebuilt
    )


def _values_equal(legacy: Any, rebuilt: Any) -> bool:
    return legacy == rebuilt


def _within_fp_tolerance(legacy: Any, rebuilt: Any) -> bool:
    if not isinstance(legacy, float) or not isinstance(rebuilt, float):
        return False
    scale = max(abs(legacy), abs(rebuilt), 1.0)
    return abs(legacy - rebuilt) <= _DOUBLE_EPS * scale


def _legacy_stdout_is_stochastic(
    result: ProbeResult,
    legacy_replay: LegacyReplay | None,
) -> bool:
    if legacy_replay is None:
        return False
    replayed = list(legacy_replay(result))
    if not replayed:
        return False
    hashes = {result.stdout_legacy_sha256}
    hashes.update(r.stdout_legacy_sha256 for r in replayed)
    return len(hashes) > 1


def _legacy_return_is_stochastic(
    result: ProbeResult,
    legacy_replay: LegacyReplay | None,
) -> bool:
    if legacy_replay is None:
        return False
    replayed = list(legacy_replay(result))
    if not replayed:
        return False
    values = {repr(result.return_value_legacy)}
    values.update(repr(r.return_value_legacy) for r in replayed)
    return len(values) > 1


def _wall_clock_distance(result: ProbeResult) -> int:
    legacy = _WALL_BUCKETS.get(result.wall_clock_bucket_legacy)
    rebuilt = _WALL_BUCKETS.get(result.wall_clock_bucket_rebuilt)
    if legacy is None or rebuilt is None:
        return 0
    return abs(legacy - rebuilt)


def _classification_detail(classified: ClassifiedProbe) -> dict[str, Any]:
    return {
        "input": classified.result.input,
        "classification": classified.classification,
    }


def _class_name_from_fqn(fqn: str) -> str:
    owner, _, _method = fqn.rpartition(".")
    return owner


def _random_probe_count() -> int:
    raw = os.environ.get("OMNIX_GATE6_RANDOM_PROBES", "100")
    try:
        return max(0, int(raw))
    except ValueError:
        return 100


def _gate_error(message: str, **details: Any) -> GateError:
    status = details.get("status", "failed")
    details["status"] = cast(Gate6Status, status)
    return GateError(
        gate_number=_GATE_NUMBER,
        gate_name=_GATE_NAME,
        message=message,
        details=details,
    )
