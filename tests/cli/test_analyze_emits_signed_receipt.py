from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from omnix.cli import main
from omnix.receipts import keystore


def _fake_studio_run(monkeypatch) -> None:
    import omnix.studio.server as server

    monkeypatch.setattr(server, "run", lambda **_kwargs: None)


def _run_analyze(
    git_repo: Path,
    home: Path,
    monkeypatch,
    make_graph_db,
    git_head,
) -> tuple[object, Path]:
    monkeypatch.setenv("HOME", str(home))
    _fake_studio_run(monkeypatch)
    make_graph_db(git_repo, git_head(git_repo))
    result = CliRunner().invoke(main, ["analyze", str(git_repo), "--no-open"])
    receipts = sorted((home / ".omnix" / "receipts").glob("analyze_*.json"))
    assert receipts, result.output
    return result, receipts[-1]


def test_analyze_writes_receipt_under_omnix_receipts_dir(
    git_repo: Path,
    make_graph_db,
    git_head,
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, receipt = _run_analyze(git_repo, tmp_path / "home", monkeypatch, make_graph_db, git_head)

    assert result.exit_code == 0, result.output
    assert receipt.parent == tmp_path / "home" / ".omnix" / "receipts"


def test_analyze_receipt_contains_commit_hash_node_count_edge_count(
    git_repo: Path,
    make_graph_db,
    git_head,
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, receipt = _run_analyze(git_repo, tmp_path / "home", monkeypatch, make_graph_db, git_head)

    assert result.exit_code == 0, result.output
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["git_commit"] == git_head(git_repo)
    assert isinstance(payload["node_count"], int)
    assert isinstance(payload["edge_count"], int)
    assert payload["node_count"] > 0
    assert payload["edge_count"] > 0


def test_analyze_receipt_has_sig_file_when_keys_present(
    git_repo: Path,
    make_graph_db,
    git_head,
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    keystore.write_keypair_dir(home / ".omnix" / "keys")

    result, receipt = _run_analyze(git_repo, home, monkeypatch, make_graph_db, git_head)

    assert result.exit_code == 0, result.output
    assert receipt.with_suffix(".sig").is_file()


def test_analyze_receipt_verifies_via_axiom_verify(
    git_repo: Path,
    make_graph_db,
    git_head,
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    key_dir = home / ".omnix" / "keys"
    keystore.write_keypair_dir(key_dir)

    result, receipt = _run_analyze(git_repo, home, monkeypatch, make_graph_db, git_head)
    verify = CliRunner().invoke(
        main,
        [
            "axiom",
            "verify",
            str(receipt),
            str(receipt.with_suffix(".sig")),
            "--pubkey",
            str(key_dir / "public.pem"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert verify.exit_code == 0, verify.output
    assert "Signature verified successfully" in verify.output


def test_analyze_skips_signing_gracefully_when_keys_absent(
    git_repo: Path,
    make_graph_db,
    git_head,
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, receipt = _run_analyze(git_repo, tmp_path / "home", monkeypatch, make_graph_db, git_head)

    assert result.exit_code == 0, result.output
    assert receipt.is_file()
    assert not receipt.with_suffix(".sig").exists()
    assert "no-omnix-key-analyze-unsigned" in result.stderr
