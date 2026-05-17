"""Layer 1 hygiene watcher (R1, R14)."""

from __future__ import annotations

import logging
from pathlib import Path
from omnix.scan.filesystem_hygiene import load_sandbox_config_from_env, validated_sandbox_roots
from omnix.scan.turboscan.hygiene_inotify import start_hygiene_watcher


class _Reg:
    def current_case(self):
        return ("probe.py", "leak", "", 1)


def test_R14_polling_fallback_logs_fallback_polling(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("OMNIX_FS_HYGIENE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_FS_HYGIENE_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("OMNIX_FS_HYGIENE_HYPOTHESIS_DIR", str(tmp_path / "h"))
    monkeypatch.setenv("OMNIX_FS_HYGIENE_VERIFY_WS", str(tmp_path / "w"))
    cfg = load_sandbox_config_from_env()
    assert cfg is not None
    roots = validated_sandbox_roots(cfg)
    sink: list = []

    def onf(d):
        sink.append(d)

    sess = start_hygiene_watcher(
        repo_root=tmp_path,
        sandbox_roots=roots,
        tmp_root=Path("/tmp"),
        registry=_Reg(),
        on_finding=onf,
        reproduction_template="pytest",
        force_polling=True,
    )
    try:
        assert any("FALLBACK_POLLING" in r.message for r in caplog.records)
    finally:
        sess.stop()
