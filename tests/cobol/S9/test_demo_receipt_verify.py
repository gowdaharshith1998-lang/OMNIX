from __future__ import annotations

from pathlib import Path


def test_demo_receipt_verify() -> None:
    assert Path("docs/COBOL_DEMO.md").is_file()
