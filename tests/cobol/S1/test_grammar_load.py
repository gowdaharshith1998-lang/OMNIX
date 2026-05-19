from __future__ import annotations

from omnix.parser.cobol.parser import parse_cobol_text


def test_abi_version_is_14() -> None:
    r = parse_cobol_text("hello.cob", "       IDENTIFICATION DIVISION.\n")
    assert r.abi_version == 14
