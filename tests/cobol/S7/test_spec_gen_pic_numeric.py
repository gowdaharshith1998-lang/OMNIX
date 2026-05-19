from __future__ import annotations

from omnix.spec.cobol_strategies import strategy_for_pic


def test_spec_gen_pic_numeric() -> None:
    assert strategy_for_pic("9(4)") is not None
