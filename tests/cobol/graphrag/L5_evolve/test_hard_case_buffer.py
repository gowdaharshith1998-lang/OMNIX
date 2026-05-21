from __future__ import annotations

from omnix.evolve.hard_case_buffer import HardCase, HardCaseBuffer
from tests.cobol.graphrag.helpers import graph


def test_age_and_capacity_pruning(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        buf = HardCaseBuffer(store)
        for idx in range(3):
            buf.append(HardCase("", f"P{idx}", "fail", "prompt", f"diff{idx}"))
        buf.prune_by_capacity(2)
        assert len(buf.get_pending_for_designer()) == 2
    finally:
        store.close()
