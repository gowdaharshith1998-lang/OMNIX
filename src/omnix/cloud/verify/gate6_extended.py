"""Additive extension to M2 Gate 6 (behavioral equivalence).

This module composes — never modifies — the existing gate6_behavioral.py.

Contract:
    extended_gate6(...)
        runs the legacy gate6_behavioral via a function reference,
        then layers Scientist + Diffy + Daikon-lite results onto the
        returned report. Output is purely additive: every field from
        the legacy gate is preserved verbatim under report["legacy_gate6"].
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from omnix.cloud.verify.daikon_lite import InvariantSet, compare as compare_invariants
from omnix.cloud.verify.diffy import DiffyReport
from omnix.cloud.verify.scientist import Mismatch


@dataclass
class ExtendedGate6Report:
    legacy_gate6: dict[str, Any] = field(default_factory=dict)
    scientist_mismatches: list[Mismatch] = field(default_factory=list)
    diffy_report: DiffyReport | None = None
    daikon_compare: dict[str, list] = field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        if self.scientist_mismatches:
            return False
        if self.diffy_report and self.diffy_report.mismatched:
            return False
        if self.daikon_compare.get("violated"):
            return False
        legacy = self.legacy_gate6
        if isinstance(legacy, dict) and legacy.get("ok") is False:
            return False
        return True


def extended_gate6(
    *,
    legacy_gate6_fn: Callable[..., dict[str, Any]],
    legacy_kwargs: dict[str, Any] | None = None,
    scientist_mismatches: list[Mismatch] | None = None,
    diffy_report: DiffyReport | None = None,
    legacy_invariants: InvariantSet | None = None,
    candidate_invariants: InvariantSet | None = None,
) -> ExtendedGate6Report:
    """Run the legacy gate, then absorb any of the new-verifier results."""
    report = ExtendedGate6Report()
    legacy_kwargs = legacy_kwargs or {}
    report.legacy_gate6 = legacy_gate6_fn(**legacy_kwargs)
    report.scientist_mismatches = list(scientist_mismatches or [])
    report.diffy_report = diffy_report
    if legacy_invariants is not None and candidate_invariants is not None:
        cmp = compare_invariants(legacy_invariants, candidate_invariants)
        report.daikon_compare = {k: list(v) for k, v in cmp.items()}
    return report
