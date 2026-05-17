"""Signed verify receipts (ML-DSA-65) — JSON envelope with inline axiom_signature."""

from __future__ import annotations

import base64
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omnix.receipts import keystore, sign
from omnix.receipts import verify as vfy

_DEFAULT_KEY = Path.home() / ".omnix" / "keys" / "secret.pem"
_DEFAULT_PUB = Path.home() / ".omnix" / "keys" / "public.pem"
_RECEIPT_DIR = Path.home() / ".omnix" / "receipts"
_TEST_KEY: Path | None = None
_TEST_PUB: Path | None = None
_TEST_RDIR: Path | None = None


def set_paths_for_tests(
    *, receipt_dir: Path | None = None, secret_path: Path | None = None
) -> None:
    global _TEST_KEY, _TEST_RDIR
    if receipt_dir is not None:
        _TEST_RDIR = receipt_dir
    if secret_path is not None:
        _TEST_KEY = secret_path


def reset_paths_for_tests() -> None:
    global _TEST_KEY, _TEST_RDIR
    _TEST_KEY = None
    _TEST_RDIR = None


def _key_path() -> Path:
    return _TEST_KEY or _DEFAULT_KEY


def _receipt_dir() -> Path:
    return _TEST_RDIR or _RECEIPT_DIR


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def split_payload_for_signing(
    body: dict[str, Any],
) -> tuple[bytes, str | None]:
    """Return canonical JSON bytes to sign; strip axiom_signature if present."""
    b = {k: v for k, v in body.items() if k != "axiom_signature"}
    raw = json.dumps(b, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return raw, body.get("axiom_signature")  # type: ignore[return-value]


def mint_signed_receipt(
    body: dict[str, Any], *, secret_pem_path: Path | None = None
) -> str:
    _sk = secret_pem_path or _key_path()
    raw, _ = split_payload_for_signing(body)
    if not _sk.is_file():
        d = {**body, "axiom_signature": None}
        return json.dumps(d, sort_keys=True, separators=(",", ":"))
    sk = keystore.secret_from_pem(_sk.read_text(encoding="ascii"))
    rnd = secrets.token_bytes(32)
    sig = sign.sign_bytes(sk, raw, b"", rnd)
    b64 = base64.b64encode(sig).decode("ascii")
    out = {**body, "axiom_signature": b64}
    return json.dumps(out, sort_keys=True, separators=(",", ":"))


def verify_signature(
    receipt: dict[str, Any],
    *,
    public_key_path: Path | None = None,
) -> bool:
    b64 = receipt.get("axiom_signature")
    if not b64 or not isinstance(b64, str):
        return False
    pubp = public_key_path or _DEFAULT_PUB
    if not pubp.is_file() and (Path.home() / ".omnix/keys/public.pem") != pubp:
        if _key_path().parent and (_key_path().parent / "public.pem").is_file():
            pubp = _key_path().parent / "public.pem"
    if not pubp.is_file():
        return False
    raw, _ = split_payload_for_signing(receipt)
    try:
        sig = base64.b64decode(b64, validate=True)
    except (ValueError, OSError, TypeError):
        return False
    try:
        pk = keystore.public_from_pem(pubp.read_text(encoding="ascii"))
    except (OSError, ValueError):
        return False
    return vfy.verify_bytes(pk, raw, b"", sig)


def write_receipt_to_disk(
    receipt_json: str, *, function_name: str, out_dir: Path | None = None
) -> Path:
    d = out_dir or _receipt_dir()
    d.mkdir(parents=True, exist_ok=True)
    tflat = _iso_utc().replace(":", "-")
    p = d / f"verify_{tflat}_{function_name}.json"
    p.write_text(receipt_json, encoding="utf-8")
    return p
