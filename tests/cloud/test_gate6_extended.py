"""Verifies that gate6_extended is purely additive."""

from __future__ import annotations

from omnix.cloud.verify.daikon_lite import Tracer, mine
from omnix.cloud.verify.diffy import DiffyReport
from omnix.cloud.verify.gate6_extended import extended_gate6
from omnix.cloud.verify.scientist import Experiment, list_publisher


def _stub_legacy_gate6(ok: bool) -> dict:
    return {"ok": ok, "gate": "behavioral", "score": 1.0 if ok else 0.0}


def test_clean_when_all_verifiers_agree():
    report = extended_gate6(
        legacy_gate6_fn=_stub_legacy_gate6,
        legacy_kwargs={"ok": True},
    )
    assert report.is_clean
    assert report.legacy_gate6["ok"] is True


def test_unclean_when_legacy_fails():
    report = extended_gate6(
        legacy_gate6_fn=_stub_legacy_gate6,
        legacy_kwargs={"ok": False},
    )
    assert not report.is_clean


def test_unclean_when_scientist_mismatch():
    mismatches = []
    exp = Experiment("e", publisher=list_publisher(mismatches))
    exp.use(lambda x: x + 1)
    exp.try_(lambda x: x + 2)
    exp.run(0)
    report = extended_gate6(
        legacy_gate6_fn=_stub_legacy_gate6,
        legacy_kwargs={"ok": True},
        scientist_mismatches=mismatches,
    )
    assert not report.is_clean


def test_unclean_when_daikon_violation():
    legacy = Tracer()
    cand = Tracer()

    @legacy.trace("f")
    def f(x):
        return x * x

    @cand.trace("f")
    def fc(x):
        return x

    for x in range(-4, 4):
        f(x)
        fc(x)

    report = extended_gate6(
        legacy_gate6_fn=_stub_legacy_gate6,
        legacy_kwargs={"ok": True},
        legacy_invariants=mine(legacy),
        candidate_invariants=mine(cand),
    )
    assert not report.is_clean
    assert "_ret >= 0" in {i.expression for i in report.daikon_compare["violated"]}


def test_unclean_when_diffy_mismatched():
    r = DiffyReport()
    # Manually mark a mismatch.
    from omnix.cloud.verify.diffy import DiffyResult
    r.absorb(DiffyResult("rq", {"a"}, {"a"}, set(), 200, 200))
    report = extended_gate6(
        legacy_gate6_fn=_stub_legacy_gate6,
        legacy_kwargs={"ok": True},
        diffy_report=r,
    )
    assert not report.is_clean
