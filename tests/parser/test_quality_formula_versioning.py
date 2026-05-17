"""Schema v1/v2/v3 evolution receipts: quality formula version resolution."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from omnix.axiom import keystore, verify as vfy
from omnix.axiom.keygen import keygen
from omnix.parser import evolution as evo


def _kpair(tmp: Path) -> None:
    pk, sk = keygen()
    kd = tmp / "keys"
    kd.mkdir()
    (kd / "public.pem").write_text(keystore.public_to_pem(pk), encoding="ascii")
    psec = kd / "secret.pem"
    psec.write_text(keystore.secret_to_pem(sk), encoding="ascii")
    os.chmod(psec, 0o600)


def test_v1_legacy_receipt_implies_formula_v1() -> None:
    d = {
        "kind": "grammar_evolution",
        "schema_version": 1,
        "grammar": "python",
    }
    assert evo.resolved_quality_formula_version_from_receipt(d) == 1


def test_v2_phase1_receipt_implies_formula_v1() -> None:
    d = {
        "kind": "grammar_evolution",
        "schema_version": 2,
        "grammar": "python",
        "added_by": evo.ADDED_AUTO,
    }
    assert evo.resolved_quality_formula_version_from_receipt(d) == 1


def test_v3_receipt_includes_quality_formula_version(tmp_path: Path) -> None:
    _kpair(tmp_path)
    evo.set_evolution_test_paths(
        receipt_dir=tmp_path / "r", secret_pem=tmp_path / "keys" / "secret.pem"
    )
    p = evo.emit_evolution_receipt_for_test(added_by=evo.ADDED_AUTO, grammar="python")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d.get("schema_version") == evo.RECEIPT_SCHEMA_V3
    assert d.get("quality_formula_version") == 2
    assert evo.resolved_quality_formula_version_from_receipt(d) == 2
    evo.reset_evolution_test_paths()


def test_v3_receipt_includes_profile_grammar_and_version(tmp_path: Path) -> None:
    _kpair(tmp_path)
    evo.set_evolution_test_paths(
        receipt_dir=tmp_path / "r2", secret_pem=tmp_path / "keys" / "secret.pem"
    )
    p = evo.emit_evolution_receipt_for_test(grammar="typescript", quality_formula_version=2)
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d.get("profile_grammar") == "typescript"
    assert int(d.get("profile_version", 0)) >= 1
    pub = (tmp_path / "keys" / "public.pem").read_text(encoding="ascii")
    sigp = (p.parent / f"{p.stem}.sig").read_text(encoding="ascii")
    pk = keystore.public_from_pem(pub)
    sig = keystore.signature_from_pem(sigp)
    assert vfy.verify_bytes(pk, p.read_bytes(), b"", sig)
    evo.reset_evolution_test_paths()


def test_v3_receipt_from_dict_resolves_quality_formula_explicits() -> None:
    d = {
        "kind": "grammar_evolution",
        "schema_version": 3,
        "grammar": "go",
        "quality_formula_version": 2,
        "profile_grammar": "go",
        "profile_version": 1,
    }
    assert evo.resolved_quality_formula_version_from_receipt(d) == 2
