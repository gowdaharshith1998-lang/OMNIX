from __future__ import annotations

from omnix.parser.cobol.copybook_resolver import build_search_paths, resolve_copybook


def test_copybook_missing(tmp_path) -> None:
    hit = resolve_copybook("MISSING", build_search_paths([str(tmp_path)]))
    assert hit is None
