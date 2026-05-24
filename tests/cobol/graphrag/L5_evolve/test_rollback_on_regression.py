from __future__ import annotations

import json
from pathlib import Path

from omnix.evolve.skill_bank import Skill, SkillBank
from tests.cobol.graphrag.helpers import graph


def test_rollback_monitor_noops_without_metrics(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        assert SkillBank(store).check_for_regression(store) == []
    finally:
        store.close()


def test_regression_monitor_flags_active_skill_with_pass_rate_drop(tmp_path) -> None:
    store = graph(tmp_path)
    runs_dir = tmp_path / ".omnix" / "runs"
    try:
        bank = SkillBank(store)
        bank.add(Skill("skill-risk", "Risky", "D", {}, "P"))
        _write_rebuild(runs_dir, "2026-05-01T000000Z-run1", "GOOD1", passed=True, skills=[])
        _write_rebuild(runs_dir, "2026-05-02T000000Z-run2", "GOOD2", passed=True, skills=[])
        _write_rebuild(runs_dir, "2026-05-03T000000Z-run3", "BAD1", passed=False, skills=["skill-risk"])
        _write_rebuild(runs_dir, "2026-05-04T000000Z-run4", "BAD2", passed=False, skills=["skill-risk"])
        _write_rebuild(runs_dir, "2026-05-05T000000Z-run5", "OK1", passed=True, skills=["skill-risk"])

        regressed = bank.check_for_regression(
            store,
            runs_dir=runs_dir,
            min_applications=3,
            drop_pct_threshold=15.0,
        )

        assert regressed == ["skill-risk"]
    finally:
        store.close()


def test_auto_rollback_invalidates_regressed_skills(tmp_path) -> None:
    store = graph(tmp_path)
    runs_dir = tmp_path / ".omnix" / "runs"
    try:
        bank = SkillBank(store)
        bank.add(Skill("skill-risk", "Risky", "D", {}, "P"))
        _write_rebuild(runs_dir, "2026-05-01T000000Z-run1", "GOOD1", passed=True, skills=[])
        _write_rebuild(runs_dir, "2026-05-02T000000Z-run2", "GOOD2", passed=True, skills=[])
        _write_rebuild(runs_dir, "2026-05-03T000000Z-run3", "BAD1", passed=False, skills=["skill-risk"])
        _write_rebuild(runs_dir, "2026-05-04T000000Z-run4", "BAD2", passed=False, skills=["skill-risk"])
        _write_rebuild(runs_dir, "2026-05-05T000000Z-run5", "OK1", passed=True, skills=["skill-risk"])

        rolled_back = bank.auto_rollback_on_regression(
            store,
            runs_dir=runs_dir,
            min_applications=3,
            drop_pct_threshold=15.0,
        )

        assert rolled_back == ["skill-risk"]
        assert [skill.skill_id for skill in bank.get_active()] == []
    finally:
        store.close()


def _write_rebuild(
    runs_dir: Path,
    run_id: str,
    program_id: str,
    *,
    passed: bool,
    skills: list[str],
) -> None:
    receipts = runs_dir / run_id / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    status = "passed" if passed else "failed"
    (receipts / f"{program_id}.json").write_text(
        json.dumps(
            {
                "gate_results": [
                    {"gate_number": n, "gate_name": str(n), "status": "passed", "details": {}}
                    for n in range(1, 6)
                ]
                + [
                    {
                        "gate_number": 6,
                        "gate_name": "behavioral_equivalence",
                        "status": status,
                        "details": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (receipts / f"{program_id}.provenance.json").write_text(
        json.dumps({"skills_applied": [{"skill_id": skill_id, "version": 1} for skill_id in skills]}),
        encoding="utf-8",
    )
