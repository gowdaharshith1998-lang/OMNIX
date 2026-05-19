from __future__ import annotations

import pytest

from omnix.spec.cobol_hypothesis import generate_spec


def test_spec_gen_no_captures(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        generate_spec("P1", tmp_path / "caps", tmp_path / "out")
