from __future__ import annotations

from omnix.gates.gate6_behavioral import compare_behavior


def test_gate6_unequal() -> None:
    d = compare_behavior(
        legacy_stdout=b"ok",
        legacy_exit=0,
        legacy_files={"a": b"1"},
        candidate_stdout=b"bad",
        candidate_exit=1,
        candidate_files={"a": b"2"},
    )
    assert not d.passed
