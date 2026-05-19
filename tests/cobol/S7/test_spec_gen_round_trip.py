from __future__ import annotations

import json

from omnix.spec.cobol_hypothesis import generate_spec


def test_spec_gen_round_trip(tmp_path) -> None:
    d = tmp_path / "caps" / "P1"
    d.mkdir(parents=True)
    (d / "a.json").write_text(json.dumps({"stdout_sha256": "x"}), encoding="utf-8")
    out = generate_spec("P1", tmp_path / "caps", tmp_path / "out")
    assert out.is_file()
