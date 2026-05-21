from __future__ import annotations

from omnix.retrieval.token_packer import pack_into_budget


def test_pack_respects_budget() -> None:
    bundle = pack_into_budget([("a", "x " * 1000), ("b", "small")], 50)
    assert bundle.estimated_tokens <= 45
    assert bundle.included


def test_safety_margin_honored() -> None:
    bundle = pack_into_budget([("a", "one two three four")], 100, safety_margin=0.5)
    assert bundle.estimated_tokens <= 50
