from __future__ import annotations

from omnix.evolve.skill_bank import Skill, SkillBank
from tests.cobol.graphrag.helpers import graph


def test_validity_windows_exclude_invalidated(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        bank = SkillBank(store)
        skill_id = bank.add(Skill("", "T", "D", {}, "P"))
        assert bank.get_active()
        bank.invalidate(skill_id)
        assert bank.get_active() == []
    finally:
        store.close()
