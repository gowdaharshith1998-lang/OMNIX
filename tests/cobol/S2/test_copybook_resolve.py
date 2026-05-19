from __future__ import annotations

from omnix.parser.cobol.copybook_resolver import build_search_paths, resolve_copybook


def test_copybook_resolve(tmp_path) -> None:
    cb = tmp_path / "CUSTOMER.cpy"
    cb.write_text("01 CUSTOMER-NAME PIC X(10).\n", encoding="utf-8")
    hit = resolve_copybook("CUSTOMER", build_search_paths([str(tmp_path)]))
    assert hit is not None
    assert hit.name == "CUSTOMER.cpy"
