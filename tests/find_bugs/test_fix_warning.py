"""--fix CLI stderr warning for non-Ollama Provider Fabric (P_E)."""

from __future__ import annotations

import pytest

from omnix.fabric.config import default_config
from omnix.find_bugs import cli as fbcli


def test_fix_warning_emits_when_chain_includes_paid_provider(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OMNIX_FUZZ_DRY", raising=False)
    c = default_config()
    c["task_chains"] = {**c.get("task_chains", {}), "code_fix": ["anthropic"]}
    c["budgets_usd_per_day"] = {**c.get("budgets_usd_per_day", {}), "anthropic": 2.0}
    monkeypatch.setattr("omnix.fabric.config.load_config", lambda: c)
    fbcli._emit_fix_fabric_warning_if_needed(True)
    err = capsys.readouterr().err
    assert "anthropic" in err
    assert "--fix" in err or "fix" in err.lower()
    assert "$" in err or "2" in err


def test_fix_warning_suppressed_when_dry_run_or_ollama_only(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_FUZZ_DRY", "1")
    c = default_config()
    c["task_chains"] = {**c.get("task_chains", {}), "code_fix": ["openai", "ollama"]}
    monkeypatch.setattr("omnix.fabric.config.load_config", lambda: c)
    fbcli._emit_fix_fabric_warning_if_needed(True)
    assert capsys.readouterr().err == ""

    monkeypatch.delenv("OMNIX_FUZZ_DRY", raising=False)
    c2 = default_config()
    c2["task_chains"] = {**c2.get("task_chains", {}), "code_fix": ["ollama"]}
    monkeypatch.setattr("omnix.fabric.config.load_config", lambda: c2)
    fbcli._emit_fix_fabric_warning_if_needed(True)
    assert capsys.readouterr().err == ""
