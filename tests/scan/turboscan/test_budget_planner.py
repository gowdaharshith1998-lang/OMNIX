"""Layer 4 budget planner (R4)."""

from __future__ import annotations

from pathlib import Path

from scan.turboscan.budget_planner import (
    analyze_python_function,
    build_budget_plan,
    examples_for_metrics,
)


def test_R4_trivial_vs_complex_examples(tmp_path: Path) -> None:
    p = tmp_path / "m.py"
    body = "\n".join(f"    x += {i}" for i in range(55))
    p.write_text(
        "def tiny(a):\n    return 1\n\ndef big(x):\n"
        + body
        + "\n    return x\n",
        encoding="utf-8",
    )
    loc_t, br_t, cy_t = analyze_python_function(p, "tiny")
    ex_t, tier_t = examples_for_metrics(loc_t, br_t, cy_t, recent_bonus=False)
    assert tier_t == "trivial"
    assert ex_t == 25
    loc_b, br_b, cy_b = analyze_python_function(p, "big")
    ex_b, tier_b = examples_for_metrics(loc_b, br_b, cy_b, recent_bonus=False)
    assert tier_b == "complex"
    assert ex_b == 200


def test_R4_plan_budget_total_matches_entries(tmp_path: Path) -> None:
    p = tmp_path / "one.py"
    p.write_text("def f(x: int) -> int:\n    return x + 1\n", encoding="utf-8")
    plan = build_budget_plan(
        tmp_path,
        [("one.py", "f", 1, p)],
        worker_slots=4,
        examples_default=100,
    )
    assert plan.worker_slots == 4
    assert len(plan.entries) == 1
    assert plan.budget_total == plan.entries[0].examples
