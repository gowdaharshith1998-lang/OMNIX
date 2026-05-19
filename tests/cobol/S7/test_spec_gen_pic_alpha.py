from __future__ import annotations

from omnix.spec.cobol_strategies import strategy_for_pic


def test_spec_gen_pic_alpha() -> None:
    assert strategy_for_pic("X(5)") is not None
