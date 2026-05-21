from __future__ import annotations

from omnix.evolve.skill_bank import SkillBank
from tests.cobol.graphrag.helpers import graph


def test_rollback_monitor_noops_without_metrics(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        assert SkillBank(store).check_for_regression(store) == []
    finally:
        store.close()
