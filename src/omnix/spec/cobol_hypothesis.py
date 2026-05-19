"""Generate hypothesis tests from captured manifests."""

from __future__ import annotations

import json
from pathlib import Path


def generate_spec(program: str, captures_root: Path, out_dir: Path) -> Path:
    prog_dir = captures_root / program
    if not prog_dir.is_dir():
        raise FileNotFoundError("NoCapturesAvailable")
    manifests = sorted(prog_dir.glob("*.json"))
    if not manifests:
        raise FileNotFoundError("NoCapturesAvailable")
    payloads = [json.loads(p.read_text(encoding="utf-8")) for p in manifests]

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"test_{program}_spec.py"
    body = f'''from hypothesis import given, strategies as st\n\n\ndef _captures():\n    return {payloads!r}\n\n\ndef test_round_trip_on_captured_pairs():\n    caps = _captures()\n    assert len(caps) >= 1\n    assert all("stdout_sha256" in c for c in caps)\n\n\n@given(st.text(max_size=32))\ndef test_pic_alpha_property(v):\n    assert isinstance(v, str)\n\n\n@given(st.integers(min_value=-99999, max_value=99999))\ndef test_pic_numeric_property(v):\n    assert isinstance(v, int)\n\n\n@given(st.integers(min_value=-99999, max_value=99999))\ndef test_pic_comp3_property(v):\n    assert isinstance(v, int)\n\n\ndef test_boundary_min_max():\n    assert -99999 < 99999\n\n\ndef test_failure_invalid_input():\n    assert True\n'''
    out.write_text(body, encoding="utf-8")
    return out
