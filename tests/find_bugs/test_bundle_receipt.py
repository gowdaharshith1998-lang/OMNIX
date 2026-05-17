"""Signed find_bugs bundle: canonical JSON and ML-DSA-65 verification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnix.find_bugs import bundle as bmod
from omnix.receipts import keystore
from omnix.verify import receipt


@pytest.fixture
def keypair_dir(tmp_path: Path) -> Path:
    d = tmp_path / "k"
    keystore.write_keypair_dir(d)
    return d


def test_assembled_is_sorted_minimal() -> None:
    body = bmod.assemble_and_sign(
        {
            "codebase_path": "/a",
            "codebase_sha256": "0" * 64,
            "file_count": 1,
            "function_count": 1,
        },
        {
            "findings_count": 0,
            "files_scanned": 1,
            "files_skipped": 0,
            "import_errors_count": 0,
            "timeout_skips_count": 0,
            "total_examples_run": 0,
            "wall_time_seconds": 0.0,
            "skipped_main_count": 0,
        },
        [],
        [],
        [],
        {
            "entry_points_detected": [],
            "clusters_detected": 0,
            "longest_call_chain_depth": 0,
        },
        no_sign=True,
    )
    assert body.index('"findings"') < body.index('"graph_signals"')
    assert " " not in body
    o = json.loads(body)
    assert o["version"] == 1 and o["kind"] == "find_bugs"
    assert o.get("skipped_main") == []


def test_sign_verify_tamper(keypair_dir: Path) -> None:
    js = bmod.assemble_and_sign(
        {
            "codebase_path": "/a",
            "codebase_sha256": "0" * 64,
            "file_count": 0,
            "function_count": 0,
        },
        {
            "findings_count": 1,
            "files_scanned": 0,
            "files_skipped": 0,
            "import_errors_count": 0,
            "timeout_skips_count": 0,
            "total_examples_run": 1,
            "wall_time_seconds": 1.0,
            "skipped_main_count": 0,
        },
        [
            {
                "file": "x.py",
                "function": "f",
                "lineno": 1,
                "severity_score": 1,
                "caller_count": 0,
                "reachable_from_entries": False,
                "cluster_id": None,
                "failures": [],
            }
        ],
        [],
        [],
        {
            "entry_points_detected": [],
            "clusters_detected": 0,
            "longest_call_chain_depth": 0,
        },
        no_sign=True,
    )
    b = {k: v for k, v in json.loads(js).items() if k != "axiom_signature"}
    s = receipt.mint_signed_receipt(  # type: ignore[call-overload, misc, arg-type]
        b, secret_pem_path=keypair_dir / "secret.pem"
    )
    obj = json.loads(s)
    assert obj.get("axiom_signature")
    assert receipt.verify_signature(
        obj, public_key_path=keypair_dir / "public.pem"
    )
    t = {**obj}
    t["summary"] = {**obj["summary"], "findings_count": 99}
    assert not receipt.verify_signature(
        t, public_key_path=keypair_dir / "public.pem"
    )
