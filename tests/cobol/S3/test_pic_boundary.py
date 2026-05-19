from __future__ import annotations

from omnix.runtime.cobol.pic_codec import validate_pic_boundary


def test_pic_boundary_signed() -> None:
    assert validate_pic_boundary(-99, digits=2, signed=True)
    assert not validate_pic_boundary(-1000, digits=2, signed=True)
