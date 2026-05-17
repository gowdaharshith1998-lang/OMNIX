"""src/fabric/receipts.py — per-call ML-DSA-65 receipts (metadata only)
Compliance: P11, P14, P18, P19
"""

from __future__ import annotations

import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SK_PATH = Path.home() / ".omnix" / "keys" / "secret.pem"
_RECEIPT_DIR = Path.home() / ".omnix" / "receipts"


def set_paths_for_tests(
    *,
    receipt_dir: Path | None = None,
    secret_path: Path | None = None,
) -> None:
    global _RECEIPT_DIR, _SK_PATH
    if receipt_dir is not None:
        _RECEIPT_DIR = receipt_dir
    if secret_path is not None:
        _SK_PATH = secret_path


def reset_paths_for_tests() -> None:
    global _RECEIPT_DIR, _SK_PATH
    _RECEIPT_DIR = Path.home() / ".omnix" / "receipts"
    _SK_PATH = Path.home() / ".omnix" / "keys" / "secret.pem"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_call_receipt(event: dict[str, Any]) -> str:
    """
    Write receipt JSON + .sig. P18: always attempt signing; stderr if unsigned.
    Returns absolute path to .json.
    """
    _RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    call_id = str(event.get("call_id", secrets.token_hex(16)))
    ts = _iso_now()
    tflat = (
        ts.replace(":", "")
        .replace("-", "")
        .replace("+0000Z", "Z")
        .replace("Z", "Z")
    )
    base = f"call_{tflat}_{call_id}"
    jpath = _RECEIPT_DIR / f"{base}.json"
    spath = _RECEIPT_DIR / f"{base}.sig"
    raw = json.dumps(event, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if not _SK_PATH.is_file():
        print(
            "no-axiom-key-fabric-unsigned-receipt",
            file=sys.stderr,
            flush=True,
        )
        jpath.write_bytes(raw)
        return str(jpath.resolve())

    from omnix.axiom import keystore, sign, verify as vfy

    sk_pem = _SK_PATH.read_text(encoding="ascii")
    sk = keystore.secret_from_pem(sk_pem)
    rnd = secrets.token_bytes(32)
    sig = sign.sign_bytes(sk, raw, b"", rnd)
    jpath.write_bytes(raw)
    spath.write_text(keystore.signature_to_pem(sig), encoding="ascii")
    pub = _SK_PATH.parent / "public.pem"
    if pub.is_file():
        pk = keystore.public_from_pem(pub.read_text(encoding="ascii"))
        sig_round = keystore.signature_from_pem(spath.read_text(encoding="ascii"))
        disk = jpath.read_bytes()
        if disk != raw or not vfy.verify_bytes(pk, disk, b"", sig_round):
            raise RuntimeError("fabric receipt self-verify failed")
    return str(jpath.resolve())
