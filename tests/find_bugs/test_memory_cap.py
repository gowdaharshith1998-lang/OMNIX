"""Memory cap: pathological allocs should be findings, not OOM kills."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("hypothesis", reason="hypothesis required")
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="resource memory caps are unavailable on Windows",
)

from omnix.find_bugs import runner


def test_memory_pathology_recorded(
    tmp_path: Path, empty_graph_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".omnix" / "receipts").mkdir(parents=True, exist_ok=True)

    f = tmp_path / "hog.py"
    f.write_text(
        textwrap.dedent(
            """
            def alloc_big(n: int) -> bytes:
                # Force an allocation above the per-verify 512MB cap for n>=1.
                _ = n
                return bytes(600_000_000)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    ex, _out, bundle = runner.run_find_bugs(
        str(tmp_path),
        examples=10,
        top=5,
        json_mode=True,
        no_bundle=True,
        include_private=False,
        max_file_size=1_000_000,
        graph_db=empty_graph_db_path,
    )
    assert ex in (0, 1)
    assert bundle is not None
    assert any(
        r.get("kind") == "memory_pathology"
        for r in (bundle.get("findings") or [])
        if isinstance(r, dict)
    )

