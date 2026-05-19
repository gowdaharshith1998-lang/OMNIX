from __future__ import annotations

import pytest

from omnix.parser.cobol.copybook_resolver import InvalidCopybookPath, build_search_paths


def test_copybook_path_traversal_rejected() -> None:
    with pytest.raises(InvalidCopybookPath):
        build_search_paths(["/tmp;rm -rf /"])
