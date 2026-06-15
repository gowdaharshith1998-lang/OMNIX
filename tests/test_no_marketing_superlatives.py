"""P_G1: no unprovable superlatives in key docs (grep-style list from polish pass)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# As spec: "first in history\|no other tool\|nobody else\|..." plus common marketing adjectives
_FORBIDDEN = (
    "first in history",
    "no other tool",
    "nobody else",
    "unique in the world",
    "first ever",
    "revolutionary",  # P_G1
    "world's first",  # P_G1
    "unprecedented",  # P_G1
    "zero competitors",  # customer-facing
)


def _paths() -> list[Path]:
    p: list[Path] = [REPO / "README.md"]
    if (REPO / "docs").is_dir():
        p.extend((REPO / "docs").rglob("*.md"))
    p.extend((REPO / "src").rglob("*.md"))
    return sorted({x for x in p if x.is_file()})


def test_docs_avoid_unprovable_superlatives() -> None:
    bad: list[str] = []
    for f in _paths():
        t = f.read_text(encoding="utf-8", errors="replace")
        lo = t.lower()
        for ph in _FORBIDDEN:
            if ph in lo:
                bad.append(f"{f}: found {ph!r}")
    assert not bad, "\n".join(bad)
