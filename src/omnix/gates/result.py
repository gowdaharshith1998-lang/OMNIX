"""GateResult + GateError — verification outcome contracts.

Every gate returns a GateError (or None) — never raises for "this code is wrong."
Crashes (gate impl bugs, JVM died, etc.) raise GateCrashError via errors.py.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class GateError:
    """Structured error from a failed gate.

    `details` is a dict of gate-specific context (e.g. for gate3: expected_signature,
    actual_signature, normalized_diff). Keep keys snake_case and JSON-serializable.
    """

    gate_number: int
    gate_name: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_number": self.gate_number,
            "gate_name": self.gate_name,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class GateResult:
    """Collected pass/fail per gate.

    No-short-circuit semantics (R-6.2): all gates run, full result set returned.
    Multiple gate failures surface different problems — losing them via early exit
    wastes signal.
    """

    gate1_passed: bool
    gate2_passed: bool
    gate3_passed: bool
    gate4_passed: bool
    gate1_error: GateError | None = None
    gate2_error: GateError | None = None
    gate3_error: GateError | None = None
    gate4_error: GateError | None = None

    @property
    def passed(self) -> bool:
        return all((self.gate1_passed, self.gate2_passed, self.gate3_passed, self.gate4_passed))

    @property
    def errors(self) -> tuple[GateError, ...]:
        return tuple(e for e in (self.gate1_error, self.gate2_error, self.gate3_error, self.gate4_error) if e is not None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate1_passed": self.gate1_passed,
            "gate2_passed": self.gate2_passed,
            "gate3_passed": self.gate3_passed,
            "gate4_passed": self.gate4_passed,
            "gate1_error": self.gate1_error.to_dict() if self.gate1_error else None,
            "gate2_error": self.gate2_error.to_dict() if self.gate2_error else None,
            "gate3_error": self.gate3_error.to_dict() if self.gate3_error else None,
            "gate4_error": self.gate4_error.to_dict() if self.gate4_error else None,
            "passed": self.passed,
        }
