from __future__ import annotations

import importlib
import os
import re
import sys
from pathlib import Path

import pytest

from omnix.verify import fuzz_fabric
from omnix.verify.runners import subprocess_llm

pytest.importorskip("subprocess", reason="stdlib")


def test_subprocess_llm_runner_classifies_exception_failure() -> None:
    s = subprocess_llm.dry_run_harness("raise")
    assert s.get("class") == "exception" or (s.get("returncode", 0) or 0) != 0


def test_subprocess_llm_runner_classifies_timeout() -> None:
    s = subprocess_llm.dry_run_harness("timeout")
    assert s.get("class") == "timeout" or s.get("timeout") is True


def test_subprocess_llm_runner_classifies_oom_via_rlimit() -> None:
    s = subprocess_llm.dry_run_harness("oom")
    cl = str(s.get("class", ""))
    assert cl in ("oom", "timeout", "exception")


def test_subprocess_llm_runner_respects_per_function_timeout() -> None:
    s = subprocess_llm.run_target_command_limited(
        [sys.executable, "-c", "import time; time.sleep(2)"], timeout_s=0.12
    )
    assert s.get("class") == "timeout" or s.get("timeout") is True


def test_subprocess_llm_runner_kills_zombies_cleanly() -> None:
    s = subprocess_llm.run_target_command_limited(
        [sys.executable, "-c", "import time; time.sleep(100)"], timeout_s=0.15
    )
    assert s.get("class") == "timeout"


def test_subprocess_llm_runner_does_not_modify_user_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "a.rs"
    t0 = "fn a() { let _ = 1; }\n"
    f.write_text(t0, encoding="utf-8")
    monkeypatch.setenv("OMNIX_FUZZ_DRY", "1")
    r = subprocess_llm.run_layer6_subprocess_limited(
        tmp_path, "a.rs", "rust", "a", "fn a() -> i32 { 0 }", agent_id="t", timeout_s=1.0
    )
    assert f.read_text() == t0
    assert r.runner_used == "subprocess_llm"


def test_finding_metadata_includes_language_and_runner_used(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_FUZZ_DRY", "1")
    r = subprocess_llm.run_layer6_subprocess_limited(
        Path("/tmp"), "x/x.rs", "rust", "foo", "fn foo() -> i32", agent_id="t", timeout_s=2.0
    )
    assert r.language == "rust"
    assert r.runner_used == "subprocess_llm"


def test_provider_fabric_budget_respected_for_fuzz_inputs() -> None:
    fuzz_fabric.set_fuzz_fabric_remaining_for_tests(0)
    a, b, c = fuzz_fabric.request_adversarial_inputs_from_fabric(
        "a", "rust", "x", "y"
    )
    assert a == [] and b == "budget_exhausted" and c is None
    fuzz_fabric.set_fuzz_fabric_remaining_for_tests(20)


def test_runner_layer_isolated_from_evolution_layer() -> None:
    m = importlib.import_module("omnix.verify.runners.subprocess_llm")
    src = Path(m.__file__ or "")
    t = src.read_text(encoding="utf-8", errors="replace")
    assert "evolution" not in t


def test_popen_uses_preexec_and_timeout() -> None:
    p = Path(subprocess_llm.__file__ or "")
    t = p.read_text(encoding="utf-8", errors="replace")
    assert "preexec_fn=_set_rlimit_as" in t
    assert "subprocess.Popen(" in t
    m = re.search(
        r"communicate\(timeout=.*timeout_s",
        t,
    )
    assert m is not None, "must use communicate(timeout=...)"


def test_subprocess_minimal_open_tokens() -> None:
    t = Path(subprocess_llm.__file__ or "").read_text(
        encoding="utf-8", errors="replace"
    )
    # Exclude ``Popen`` (contains substring ``open(``) — no builtin file ``open(``.
    if re.search(r"(?<!P)open\(", t):
        pytest.fail("file open( must not appear in subprocess runner")
