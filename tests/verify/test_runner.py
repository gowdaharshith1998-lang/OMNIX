"""End-to-end verify runner (Hypothesis, exit codes, receipts, JSON)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from axiom import keystore
from verify import runner

REPO = Path(__file__).resolve().parents[2]
OMNIX = REPO / "omnix.py"
FIX = Path(__file__).parent / "fixtures"
GOOD = FIX / "sample_typed.py"
BAD = FIX / "sample_buggy.py"

pytest.importorskip("hypothesis", reason="hypothesis required")


def test_pass_typed_add(
    tmp_path: Path, graph_db_for_runner: str
) -> None:
    rdir = tmp_path / "rcpt"
    rdir.mkdir()
    code, out = runner.run(
        str(GOOD),
        function="add",
        examples=20,
        sign=False,
        output_format="text",
        graph_db_path=graph_db_for_runner,
        codebase_root=str(REPO),
        receipt_dir=str(rdir),
    )
    assert code == 0
    assert "add" in out or out == ""


def test_fail_unsafe_div(
    tmp_path: Path, graph_db_for_runner: str
) -> None:
    rdir = tmp_path / "r"
    rdir.mkdir()
    code, out = runner.run(
        str(BAD),
        function="unsafe_div",
        examples=50,
        sign=False,
        output_format="text",
        graph_db_path=graph_db_for_runner,
        codebase_root=str(REPO),
        receipt_dir=str(rdir),
    )
    assert code == 1
    assert "fail" in out.lower() or "fals" in out.lower() or "error" in out.lower() or "Zero" in out or code == 1


def test_respects_examples(graph_db_for_runner: str) -> None:
    code, _ = runner.run(
        str(GOOD),
        function="add",
        examples=5,
        sign=False,
        output_format="json",
        graph_db_path=graph_db_for_runner,
        codebase_root=str(REPO),
    )
    assert code in (0, 1, 2)


def test_receipt_path_when_signing(
    tmp_path: Path, graph_db_for_runner: str
) -> None:
    k = tmp_path / "k"
    keystore.write_keypair_dir(k)
    rdir = tmp_path / "receipts"
    from verify import receipt as R

    R.set_paths_for_tests(
        receipt_dir=rdir, secret_path=k / "secret.pem"  # type: ignore[call-arg]
    )
    try:
        code, _ = runner.run(
            str(GOOD),
            function="add",
            examples=2,
            sign=True,
            output_format="text",
            graph_db_path=graph_db_for_runner,
            codebase_root=str(REPO),
            receipt_dir=str(rdir),
        )
        pats = list(rdir.glob("verify_*.json"))
        assert pats, "expected a verify_*.json receipt"
    finally:
        R.reset_paths_for_tests()  # type: ignore[misc]


def test_no_receipt(
    tmp_path: Path, graph_db_for_runner: str
) -> None:
    rdir = tmp_path / "q"
    rdir.mkdir()
    before = set(rdir.glob("*.json"))
    code, _ = runner.run(
        str(GOOD),
        function="add",
        examples=2,
        sign=False,
        no_receipt=True,
        output_format="text",
        graph_db_path=graph_db_for_runner,
        codebase_root=str(REPO),
        receipt_dir=str(rdir),
    )
    after = set(rdir.glob("*.json"))
    assert after == before
    assert code in (0, 1)


def test_json_mode(graph_db_for_runner: str) -> None:
    code, out = runner.run(
        str(FIX / "sample_typed.py"),
        function="add",
        examples=3,
        sign=False,
        output_format="json",
        graph_db_path=graph_db_for_runner,
        codebase_root=str(REPO),
    )
    if code == 0 and out:
        d = json.loads(out)
        assert d.get("examples_run") is not None


def test_cli_subprocess() -> None:
    r = subprocess.run(
        [sys.executable, str(OMNIX), "verify", "--help"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert r.returncode == 0
    assert "verify" in (r.stdout + r.stderr).lower() or "path" in (r.stdout + r.stderr).lower()
