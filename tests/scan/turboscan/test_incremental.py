"""Layer 6 incremental paths (R6)."""

from __future__ import annotations

import json
from pathlib import Path

from scan.turboscan.incremental import (
    filter_incremental_paths,
    write_last_green_scan,
)
from scan.turboscan.types import turboscan_last_scan_path


def _relp(pa: Path, root: Path) -> str:
    return pa.resolve().relative_to(root.resolve()).as_posix()


def test_R6_filter_keeps_all_when_no_marker(tmp_path: Path) -> None:
    p = tmp_path / "a.py"
    p.write_text("x=1\n", encoding="utf-8")
    out = filter_incremental_paths(tmp_path, [p], relpos_fn=_relp)
    assert out == [p]


def test_R6_filter_after_marker_writes(tmp_path: Path) -> None:
    p = tmp_path / "b.py"
    p.write_text("x=1\n", encoding="utf-8")
    write_last_green_scan(tmp_path)
    marker = turboscan_last_scan_path(tmp_path)
    assert marker.is_file()
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert "mtime_epoch" in data
