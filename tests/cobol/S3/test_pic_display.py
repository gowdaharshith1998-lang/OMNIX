from __future__ import annotations

from omnix.runtime.cobol.pic_codec import parse_pic


def test_pic_display_parse() -> None:
    p = parse_pic("X(10)")
    assert p.kind == "alpha"
    assert p.digits == 10
