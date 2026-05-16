"""P_B1: no dynamic attribute tricks on ``subprocess`` in Layer 6 runner."""

from __future__ import annotations

import re
from pathlib import Path

_RUNNER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "omnix"
    / "verify"
    / "runners"
    / "subprocess_llm.py"
)


def test_subprocess_llm_no_dynamic_attr_lookup_on_subprocess() -> None:
    t = _RUNNER.read_text(encoding="utf-8", errors="replace")
    assert "getattr(subprocess" not in t
    assert re.search(r'"P"\s*\+\s*"open"', t) is None
    assert "subprocess.Popen(" in t
