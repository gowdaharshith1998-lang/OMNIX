"""Crash-level errors for omnix.gates.

Distinct from GateError (a structured failure result): GateCrashError signals the
gate impl itself blew up (JVM died, JAR missing, fs permissions). Orchestrator
decides whether to retry, escalate, or fail the whole run.
"""

from __future__ import annotations


class GateCrashError(Exception):
    """A gate implementation crashed — distinct from a gate failure result.

    `gate_number` indicates which gate; `original` retains the underlying exception
    so the orchestrator can attach it to a `requires_human_review` record.
    """

    def __init__(self, gate_number: int, message: str, original: Exception | None = None) -> None:
        self.gate_number = gate_number
        self.original = original
        super().__init__(f"gate {gate_number} crashed: {message}")
