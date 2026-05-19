from __future__ import annotations

from pathlib import Path

import pytest

from omnix.runtime.cobol.gnucobol_adapter import compile_cobol


def test_gnucobol_compile_failure(tmp_path: Path) -> None:
    src = tmp_path / "x.cob"
    src.write_text("bad", encoding="utf-8")
    with pytest.raises(RuntimeError):
        compile_cobol(src, out_dir=tmp_path)
