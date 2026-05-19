from __future__ import annotations

from decimal import Decimal

from omnix.runtime.cobol.pic_codec import decode_comp3, encode_comp3, parse_pic


def test_tc401p_comp3_scaled_decimal_roundtrip() -> None:
    spec = parse_pic("S9(7)V99 COMP-3")
    raw = encode_comp3(Decimal("105250.00"), digits=spec.digits, signed=spec.signed, scale=spec.scale)

    assert spec.digits == 9
    assert spec.scale == 2
    assert decode_comp3(raw, digits=spec.digits, signed=spec.signed, scale=spec.scale) == Decimal("105250.00")


def test_tc401p_rate_pic_clause() -> None:
    spec = parse_pic("S9(3)V9(4) COMP-3")

    assert spec.digits == 7
    assert spec.scale == 4
    assert spec.signed
