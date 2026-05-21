from __future__ import annotations

from omnix.evolve.dual_evolve import parse_failure_analysis


def test_failure_analysis_parses_to_instruction() -> None:
    assert "newline" in parse_failure_analysis("newline mismatch")
