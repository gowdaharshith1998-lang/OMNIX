"""Runner — execute all four gates without short-circuiting (R-6.2).

Crashes (GateCrashError) are caught per-gate and surfaced as a structured
GateError with message `crashed: ...`, so a JVM failure on gate 1 doesn't
discard the signal from gate 3.
"""

from __future__ import annotations

from omnix.gates import gate1_syntactic, gate2_typecheck, gate3_signature, gate4_dependency
from omnix.gates.errors import GateCrashError
from omnix.gates.result import GateError, GateResult
from omnix.orchestrator.attempt import RebuildAttempt
from omnix.spec import Spec

_GATE_NAMES = {
    1: "syntactic",
    2: "typecheck",
    3: "signature",
    4: "dependency",
}


def _crash_to_error(crash: GateCrashError, gate_number: int) -> GateError:
    return GateError(
        gate_number=gate_number,
        gate_name=_GATE_NAMES[gate_number],
        message=f"crashed: {crash}",
        details={
            "crash": True,
            "original_type": type(crash.original).__name__ if crash.original else None,
            "original_message": str(crash.original) if crash.original else None,
        },
    )


def run(
    rebuild_attempt: RebuildAttempt,
    spec: Spec,
    source_code: str | None = None,
) -> GateResult:
    """Run gates 1-4 in order, return a populated GateResult.

    Does NOT short-circuit (R-6.2): every gate runs even if earlier ones failed,
    because each gate surfaces a different class of problem.
    """
    code = source_code if source_code is not None else rebuild_attempt.response_text

    # Gate 1.
    try:
        err1 = gate1_syntactic.check(code)
    except GateCrashError as crash:
        err1 = _crash_to_error(crash, 1)
    gate1_passed = err1 is None

    # Gate 2.
    try:
        err2 = gate2_typecheck.check(code)
    except GateCrashError as crash:
        err2 = _crash_to_error(crash, 2)
    gate2_passed = err2 is None

    # Gate 3.
    try:
        err3 = gate3_signature.check(code, spec.signature)
    except GateCrashError as crash:
        err3 = _crash_to_error(crash, 3)
    gate3_passed = err3 is None

    # Gate 4.
    try:
        err4 = gate4_dependency.check(code, spec.dependencies)
    except GateCrashError as crash:
        err4 = _crash_to_error(crash, 4)
    gate4_passed = err4 is None

    return GateResult(
        gate1_passed=gate1_passed,
        gate2_passed=gate2_passed,
        gate3_passed=gate3_passed,
        gate4_passed=gate4_passed,
        gate1_error=err1,
        gate2_error=err2,
        gate3_error=err3,
        gate4_error=err4,
    )
