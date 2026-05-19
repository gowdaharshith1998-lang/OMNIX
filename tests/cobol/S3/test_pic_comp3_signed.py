from __future__ import annotations

from omnix.runtime.cobol.pic_codec import decode_comp3, encode_comp3


def test_pic_comp3_signed_roundtrip() -> None:
    raw = encode_comp3(-1234, digits=4, signed=True)
    assert int(decode_comp3(raw, digits=4, signed=True)) == -1234
