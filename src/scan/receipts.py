# Compliance: P11, P5

"""
AXIOM ML-DSA-65 receipts for scan events (no plaintext keys).

Compliance: P5, P11, P8
"""

from __future__ import annotations

import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

_SK_PATH = Path.home() / ".omnix" / "keys" / "secret.pem"
_RECEIPT_DIR = Path.home() / ".omnix" / "receipts"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json_and_sig(
    event_obj: dict,
    file_prefix: str,
) -> str | None:
    """
    Write event JSON and detached .sig (sign_bytes over raw JSON bytes).
    Returns absolute path to .json for response, or None on skip.
    """
    _RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    short = secrets.token_hex(4)
    ts = _iso_now()
    tflat = (
        ts.replace(":", "-")
        .replace("+0000Z", "Z")
        .replace("Z", "")
        .replace("T", "_")
    )
    base = f"{file_prefix}_{tflat}_{short}"
    jpath = _RECEIPT_DIR / f"{base}.json"
    spath = _RECEIPT_DIR / f"{base}.sig"
    raw = json.dumps(event_obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if not _SK_PATH.is_file():
        print("no-axiom-key-scan-unsigned", file=sys.stderr, flush=True)
        jpath.write_bytes(raw)
        return str(jpath)

    from axiom import keystore, sign

    sk_pem = _SK_PATH.read_text(encoding="ascii")
    sk = keystore.secret_from_pem(sk_pem)
    rnd = secrets.token_bytes(32)
    sig = sign.sign_bytes(sk, raw, b"", rnd)
    jpath.write_bytes(raw)
    spath.write_text(keystore.signature_to_pem(sig), encoding="ascii")
    return str(jpath)


def write_vault_scan_receipt(
    *,
    sources_scanned: list[str],
    detections_found: int,
    host: str,
) -> str | None:
    event = {
        "event": "vault.scan",
        "timestamp": _iso_now(),
        "sources_scanned": sources_scanned,
        "detections_found": int(detections_found),
        "host": host,
    }
    return _write_json_and_sig(event, "scan")


def write_scan_expired_receipt(*, detection_count: int) -> str | None:
    event = {
        "event": "vault.scan.expired",
        "timestamp": _iso_now(),
        "detection_count": int(detection_count),
    }
    return _write_json_and_sig(event, "scan_expired")
