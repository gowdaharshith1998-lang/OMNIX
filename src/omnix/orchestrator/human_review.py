"""Human-review records + retry-run report.

These dataclasses are the receipt-friendly outputs of `run_with_retry`. Frozen
for value-semantics and to make them safe to hand off to the receipts layer.

`HumanReviewRecord` retains the FULL attempt + gate trail (R-7.5) — every prompt
hash, every response hash, every gate result — so a reviewer can reproduce what
the LLM tried and why each attempt failed.

`RetryRunReport` is the top-level outcome: which nodes passed, which need a human,
and the flat list of every attempt for auditability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from omnix.gates.result import GateError, GateResult
from omnix.orchestrator.attempt import RebuildAttempt


@dataclass(frozen=True)
class HumanReviewRecord:
    """Tamper-evident history for a node that exhausted retries.

    Contains ALL attempts (not just the final one) per R-7.5 — full prompt_hash,
    response_hash, gate_result trail. Receipts can serialize this verbatim.
    """

    node_fqn: str
    attempts: tuple[RebuildAttempt, ...]
    gate_results: tuple[GateResult, ...]
    final_gate_errors: tuple[GateError, ...]
    reason: str = "max_retries_exhausted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_fqn": self.node_fqn,
            "reason": self.reason,
            "attempts": [a.to_dict() for a in self.attempts],
            "gate_results": [gr.to_dict() for gr in self.gate_results],
            "final_gate_errors": [e.to_dict() for e in self.final_gate_errors],
        }


@dataclass(frozen=True)
class RetryRunReport:
    """Output of `run_with_retry`.

    `successful_attempts` holds the *final* (passing) RebuildAttempt per node that
    succeeded. `flagged_for_human_review` holds one HumanReviewRecord per node that
    exhausted `max_retries`. `full_attempt_history` is every attempt across every
    node in dispatch order — useful for cost/telemetry post-hoc analysis.
    """

    successful_attempts: tuple[RebuildAttempt, ...]
    flagged_for_human_review: tuple[HumanReviewRecord, ...]
    full_attempt_history: tuple[RebuildAttempt, ...]

    @property
    def total_attempts(self) -> int:
        return len(self.full_attempt_history)

    @property
    def success_count(self) -> int:
        return len(self.successful_attempts)

    @property
    def review_count(self) -> int:
        return len(self.flagged_for_human_review)

    def to_dict(self) -> dict[str, Any]:
        return {
            "successful_attempts": [a.to_dict() for a in self.successful_attempts],
            "flagged_for_human_review": [r.to_dict() for r in self.flagged_for_human_review],
            "full_attempt_history": [a.to_dict() for a in self.full_attempt_history],
            "total_attempts": self.total_attempts,
            "success_count": self.success_count,
            "review_count": self.review_count,
        }
