"""Hypothesis strategies for COBOL PIC clauses."""

from __future__ import annotations

import re

from hypothesis import strategies as st


def strategy_for_pic(pic: str):
    up = pic.upper().replace(" ", "")
    if up.startswith("X(") and up.endswith(")"):
        n = int(up[2:-1])
        return st.text(min_size=0, max_size=n)
    m = re.match(r"^(S)?9\((\d+)\)$", up)
    if m:
        d = int(m.group(2))
        maxv = 10**d - 1
        if m.group(1):
            return st.integers(min_value=-maxv, max_value=maxv)
        return st.integers(min_value=0, max_value=maxv)
    return st.text(min_size=0, max_size=32)
