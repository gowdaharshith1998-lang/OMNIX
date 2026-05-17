from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from omnix.studio.server import app
from omnix.studio.workspace import MANAGER, open_workspace


def _open_managed_workspace(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> str:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "global"))
    w, _stats = open_workspace(str(root))
    MANAGER.put(w)
    return w.id


def _cleanup_workspace(workspace_id: str) -> None:
    w = MANAGER.get(workspace_id)
    if w is not None:
        asyncio.run(w.stop())
    MANAGER.remove(workspace_id)


def _write_keypair(keys_dir: Path) -> tuple[Path, Path]:
    from omnix.axiom import keygen, keystore  # type: ignore[import-not-found]

    pk, sk = keygen.keygen()
    keys_dir.mkdir(parents=True, exist_ok=True)
    pubp = keys_dir / "public.pem"
    seck = keys_dir / "secret.pem"
    pubp.write_text(keystore.public_to_pem(pk), encoding="ascii")
    seck.write_text(keystore.secret_to_pem(sk), encoding="ascii")
    return pubp, seck


def _sign_detached(json_path: Path, sig_path: Path, secret_pem: Path) -> None:
    from omnix.axiom import keystore, sign  # type: ignore[import-not-found]

    sk = keystore.secret_from_pem(secret_pem.read_text(encoding="ascii"))
    raw = json_path.read_bytes()
    sig = sign.sign_bytes(sk, raw, b"", rnd=b"\x11" * 32)
    sig_path.write_text(keystore.signature_to_pem(sig), encoding="ascii")


def test_receipts_list_verification_states_and_get_by_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "proj"
    project.mkdir()

    home = tmp_path / "home"
    receipts_dir = home / ".omnix" / "receipts"
    keys_dir = home / ".omnix" / "keys"
    receipts_dir.mkdir(parents=True)
    pubp, seck = _write_keypair(keys_dir)
    assert pubp.is_file() and seck.is_file()

    # Verified receipt
    r1 = receipts_dir / "call_20260429Z_ok.json"
    r1.write_text(json.dumps({"event": "fabric.call", "call_id": "ok"}, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    _sign_detached(r1, receipts_dir / "call_20260429Z_ok.sig", seck)

    # Tampered receipt: signature present but JSON mutated after signing.
    r2 = receipts_dir / "call_20260429Z_bad.json"
    r2.write_text(json.dumps({"event": "fabric.call", "call_id": "bad"}, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    _sign_detached(r2, receipts_dir / "call_20260429Z_bad.sig", seck)
    r2.write_text(json.dumps({"event": "fabric.call", "call_id": "bad", "tampered": True}, sort_keys=True, separators=(",", ":")), encoding="utf-8")

    # Unsigned receipt
    r3 = receipts_dir / "call_20260429Z_unsigned.json"
    r3.write_text(json.dumps({"event": "fabric.call", "call_id": "u"}, sort_keys=True, separators=(",", ":")), encoding="utf-8")

    monkeypatch.setattr(Path, "home", lambda: home)

    workspace_id = _open_managed_workspace(project, tmp_path, monkeypatch)
    try:
        client = TestClient(app)
        res = client.get(f"/api/workspace/{workspace_id}/receipts?limit=50")
        assert res.status_code == 200
        rows = res.json()["receipts"]
        by_id = {r["receipt_id"]: r for r in rows}

        ok = by_id["call_20260429Z_ok"]
        bad = by_id["call_20260429Z_bad"]
        unsigned = by_id["call_20260429Z_unsigned"]

        assert ok["has_signature"] is True
        assert ok["verified"] is True

        assert bad["has_signature"] is True
        assert bad["verified"] is False

        assert unsigned["has_signature"] is False
        assert unsigned["verified"] is False

        # GET-by-id returns full JSON payload.
        body = client.get(f"/api/workspace/{workspace_id}/receipts/call_20260429Z_ok").json()["receipt"]
        assert body == {"call_id": "ok", "event": "fabric.call"}
    finally:
        _cleanup_workspace(workspace_id)

