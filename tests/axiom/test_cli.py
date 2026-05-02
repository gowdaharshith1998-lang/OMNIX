"""Integration: `omnix axiom` Click commands."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from click.testing import CliRunner

from cli import main


def test_main_exposes_analyze_grammar_axiom() -> None:
    """Pip entry `omnix` must register analyze (Studio) alongside grammar and axiom."""
    names = set(main.commands.keys())
    assert "analyze" in names
    assert "grammar" in names
    assert "axiom" in names


def test_keygen_creates_pem_and_mode() -> None:
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        r = runner.invoke(main, ["axiom", "keygen", "--out", str(t)])
        assert r.exit_code == 0, r.output
        pub = t / "public.pem"
        sec = t / "secret.pem"
        assert pub.is_file() and sec.is_file()
        assert (os.stat(sec).st_mode & 0o777) == 0o600


def test_keygen_fails_unwritable() -> None:
    runner = CliRunner()
    r = runner.invoke(main, ["axiom", "keygen", "--out", "/nonexistent_root_omnix_x/w"])
    assert r.exit_code == 1


def test_sign_verify_roundtrip_cli() -> None:
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        r = runner.invoke(main, ["axiom", "keygen", "--out", str(base)])
        assert r.exit_code == 0
        doc = base / "msg.bin"
        doc.write_bytes(b"cli test content")
        sigp = base / "out.sig"
        r2 = runner.invoke(
            main,
            [
                "axiom",
                "sign",
                str(doc),
                "--key",
                str(base / "secret.pem"),
                "--out",
                str(sigp),
            ],
        )
        assert r2.exit_code == 0, r2.output
        r3 = runner.invoke(
            main,
            [
                "axiom",
                "verify",
                str(doc),
                str(sigp),
                "--pubkey",
                str(base / "public.pem"),
            ],
        )
        assert r3.exit_code == 0
        assert "Signature verified successfully" in r3.output
        doc.write_bytes(b"tamper")
        r4 = runner.invoke(
            main,
            [
                "axiom",
                "verify",
                str(doc),
                str(sigp),
                "--pubkey",
                str(base / "public.pem"),
            ],
        )
        assert r4.exit_code == 1
        assert "Signature verification FAILED" in r4.output
