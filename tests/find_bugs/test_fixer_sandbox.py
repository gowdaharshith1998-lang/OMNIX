"""Layer 7 fixer: sandbox, baseline gate, and mock ``code_fix`` (P28)."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest import mock

import pytest

from omnix.find_bugs import fixer, fix_fabric, runner, sandbox
from omnix.find_bugs.fixer import orchestrate_code_fix


def _write_min_repo(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        "[project]\nname = \"t\"\nversion = \"0\"\n", encoding="utf-8"
    )
    (root / "buggy.py").write_text(
        textwrap.dedent(
            """
            def divide(x, y):
                return x // y
        """
        ).lstrip(),
        encoding="utf-8",
    )
    td = root / "tests"
    td.mkdir()
    (td / "test_smoke.py").write_text(
        textwrap.dedent(
            """
            import pathlib
            import sys
            p = pathlib.Path(__file__).resolve().parents[1]
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
            import buggy

            def test_import_works():
                assert buggy
        """
        ).lstrip(),
        encoding="utf-8",
    )


def _write_broken_test_repo(root: Path) -> None:
    _write_min_repo(root)
    (root / "tests" / "test_smoke.py").write_text(
        textwrap.dedent(
            """
            def test_fail():
                assert 1 == 0
        """
        ).lstrip(),
        encoding="utf-8",
    )


def test_sandbox_write_guard_rejects_nontmp() -> None:
    with pytest.raises(ValueError, match="P26"):
        sandbox.assert_write_allowed(Path("/var") / "x" / "y.z")


@mock.patch.dict(os.environ, {"OMNIX_CODE_FIX_MOCK": "1"}, clear=False)
def test_baseline_failing_stops_with_status(tmp_path: Path) -> None:
    _write_broken_test_repo(tmp_path)
    fix_fabric.set_code_fix_remaining_for_tests(10)
    o = orchestrate_code_fix(
        repo_root=tmp_path,
        rel_failing="buggy.py",
        function_name="divide",
        language="python",
        original_failure={"file": "buggy.py", "function": "divide", "x": 1},
        graph_db=None,
    )
    assert o.success is False
    assert o.message == "baseline_test_suite_failing"
    b = o.body
    assert b.get("status") == "baseline_test_suite_failing"
    assert b.get("cleanup_succeeded") is True


@mock.patch("omnix.find_bugs.fixer._pbt_sandbox", return_value=True)
@mock.patch.dict(os.environ, {"OMNIX_CODE_FIX_MOCK": "1"}, clear=False)
def test_suggested_fix_receipt_body(_mock_pbt: object, tmp_path: Path) -> None:
    _write_min_repo(tmp_path)
    fix_fabric.set_code_fix_remaining_for_tests(10)
    o = orchestrate_code_fix(
        repo_root=tmp_path,
        rel_failing="buggy.py",
        function_name="divide",
        language="python",
        original_failure={"file": "buggy.py", "function": "divide", "x": 1},
        graph_db=None,
    )
    assert o.success is True
    assert o.body.get("status") == "suggested"
    assert o.body.get("cleanup_succeeded") is True
    d = o.body.get("fix", {})
    assert "diff" in d
    assert o.body.get("n_graph_edges") == 0


def test_not_python_rejected() -> None:
    o = orchestrate_code_fix(
        repo_root=Path("/"),
        rel_failing="a.rs",
        function_name="x",
        language="rust",
        original_failure={},
        graph_db=None,
    )
    assert o.message == "language_not_supported_5c"
    assert o.success is False


def test_layer7_filter_helper() -> None:
    assert runner._layer7_python_fixable(  # noqa: SLF001
        {
            "file": "a.py",
            "function": "f",
            "failures": [],
        }
    )
    assert not runner._layer7_python_fixable(  # noqa: SLF001
        {
            "kind": "memory_pathology",
            "file": "a.py",
            "function": "f",
        }
    )
    assert not runner._layer7_python_fixable(  # noqa: SLF001
        {
            "file": "a.rs",
            "function": "f",
            "language": "rust",
        }
    )


def test_run_test_suite_sandbox_respects_cwd() -> None:
    from omnix.find_bugs import test_detect

    s = test_detect.TestRunnerSpec("none", [], order_chosen=["(none)"])
    r0 = fixer.run_test_suite_sandbox(Path("/nope"), s)
    assert r0["exit"] == 1
    assert "no test runner" in (r0.get("stderr") or "")


def test_grep_safety_fixer_sandbox() -> None:
    """Adversarial guardrails: no risky patterns in new Layer 7 modules."""
    root = Path("src/omnix/find_bugs")
    for name in ("fixer.py", "sandbox.py"):
        t = (root / name).read_text(encoding="utf-8")
        for bad in (
            "shell=True",
            "rmtree(",
        ):
            if name == "sandbox.py" and bad == "rmtree(":
                continue
            assert bad not in t, f"{name} must not contain {bad!r}"
    sb = (root / "sandbox.py").read_text(encoding="utf-8")
    assert 'prefix="omnix_fix_"' in sb
    assert 'dir="/tmp"' in sb
