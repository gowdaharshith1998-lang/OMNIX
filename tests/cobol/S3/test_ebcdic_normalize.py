from __future__ import annotations

from omnix.runtime.cobol.ebcdic import normalize_ebcdic


def test_ebcdic_normalize_no_detect_pass_through() -> None:
    assert normalize_ebcdic(b"HELLO", no_detect=True) == "HELLO"
