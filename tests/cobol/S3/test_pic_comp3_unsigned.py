from __future__ import annotations

from omnix.runtime.cobol.pic_codec import decode_comp3, encode_comp3


def test_pic_comp3_unsigned_roundtrip() -> None:
    raw = encode_comp3(9876, digits=4, signed=False)
    assert int(decode_comp3(raw, digits=4, signed=False)) == 9876
