from __future__ import annotations

import asyncio

from omnix.enrich.mock_provider import MockEnrichmentProvider
from omnix.evolve.designer import run_designer
from omnix.evolve.hard_case_buffer import HardCase, HardCaseBuffer
from omnix.evolve.skill_bank import SkillBank
from tests.cobol.graphrag.helpers import graph


def test_designer_mints_skill_from_buffer(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        buf = HardCaseBuffer(store)
        buf.append(HardCase("", "A", "fail", "prompt", "diff"))
        buf.append(HardCase("", "B", "fail", "prompt", "diff"))
        report = asyncio.run(run_designer(store, buf, MockEnrichmentProvider()))
        assert report.skills_minted >= 1
        assert SkillBank(store).get_active()
    finally:
        store.close()
