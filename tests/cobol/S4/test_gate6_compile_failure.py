from __future__ import annotations

import pytest

from omnix.runtime.cobol.gnucobol_adapter import compile_cobol


def test_gate6_compile_failure(tmp_path) -> None:
    src = tmp_path / "bad.cob"
    src.write_text("bad", encoding="utf-8")
    with pytest.raises(RuntimeError):
        compile_cobol(src, out_dir=tmp_path)
