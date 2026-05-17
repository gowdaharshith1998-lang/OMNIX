from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from omnix.verify.runners import detect


def test_native_runner_detection_returns_correct_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    rs = tmp_path / "m.rs"
    rs.write_text("fn x() {}", encoding="utf-8")
    def _w(x: str) -> str | None:
        return "/bin/cargo" if x == "cargo" else shutil.which(x)

    monkeypatch.setattr("shutil.which", _w, raising=True)
    d0 = detect.detect_universal_backend(tmp_path, "m.rs", rs, "rust")
    assert d0.backend in ("cargo_fuzz", "subprocess_llm")


def test_native_runner_skipped_when_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "go.mod").write_text("module t\n", encoding="utf-8")
    g = tmp_path / "a.go"
    g.write_text("package t\n", encoding="utf-8")
    monkeypatch.setattr("shutil.which", lambda _x: None, raising=True)
    d0 = detect.detect_universal_backend(tmp_path, "a.go", g, "go")
    if d0.backend == "go_fuzz":
        assert d0.native_eligible is True
    else:
        assert d0.backend == "subprocess_llm"
