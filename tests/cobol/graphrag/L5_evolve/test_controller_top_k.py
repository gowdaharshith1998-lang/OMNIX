from __future__ import annotations

from omnix.evolve.controller import select_skills_for
from omnix.evolve.skill_bank import Skill, SkillBank
from tests.cobol.graphrag.helpers import graph, mark_enriched


def test_cosine_similarity_ranks_top_k(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        mark_enriched(store)
        bank = SkillBank(store)
        bank.add(Skill("", "HELLO skill", "HELLO signature", {"contains": "HELLO"}, "P"))
        bank.add(Skill("", "Other skill", "unrelated", {}, "Q"))
        assert select_skills_for("prog:HELLO", store, bank, top_k=1)[0].title == "HELLO skill"
    finally:
        store.close()
