"""Phase 3c: LEGACY_LANGUAGE_SUPPORT must not list roadmap-only languages as supported."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_DOC = _REPO / "docs" / "LEGACY_LANGUAGE_SUPPORT.md"


def _supported_section() -> str:
    text = _DOC.read_text(encoding="utf-8")
    m = re.search(
        r"^## Supported today\n(?P<body>.*?)(?=^## .)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert m is not None, "expected '## Supported today' section in LEGACY doc"
    return m.group("body")


@pytest.mark.skipif(
    not _DOC.is_file(), reason="docs/LEGACY_LANGUAGE_SUPPORT.md not present"
)
def test_legacy_doc_has_no_rpg_pli_jcl_in_supported_section() -> None:
    # Roadmap (Integration #15) languages: must not appear in Supported today.
    supported = _supported_section()
    for pattern in (r"\bRPG\b", r"PL[-/]I", r"\bJCL\b", r"VB6"):
        assert re.search(pattern, supported, re.IGNORECASE) is None, (
            f"forbidden ref {pattern!r} in supported section: {supported[:200]!r}…"
        )
