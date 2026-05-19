from __future__ import annotations

from omnix.spec.cobol_strategies import strategy_for_pic


def test_spec_gen_pic_comp3() -> None:
    assert strategy_for_pic("S9(4)") is not None
