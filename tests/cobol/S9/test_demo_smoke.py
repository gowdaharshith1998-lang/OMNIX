from __future__ import annotations

from pathlib import Path


def test_demo_smoke() -> None:
    assert Path("docs/cobol_demo.sh").is_file()
