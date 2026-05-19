from __future__ import annotations

from omnix.runtime.cobol.ebcdic import detect_ebcdic


def test_ebcdic_detect_true() -> None:
    data = bytes([0xC1, 0xC2, 0x4B, 0xC3, 0xC4, 0xC5] * 20)
    assert detect_ebcdic(data)
