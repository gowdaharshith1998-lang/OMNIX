# Compliance: P11, P12, P13, P21

"""
HTTP handlers for /api/vault/scan and /api/vault/scan/consume.

Compliance: P11, P12, P13, P21
"""

from __future__ import annotations

import json
import re
import secrets
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from . import patterns
from .receipts import write_vault_scan_receipt
from .scanner import run_scan
from .store import get_detection_store


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_host_hostname(host_header: str) -> str:
    h = host_header.strip()
    if h.startswith("["):
        end = h.find("]")
        if end > 0:
            return h[: end + 1].lower()
    return h.split(":")[0].strip().lower()


def is_localhost_request(handler: BaseHTTPRequestHandler) -> bool:
    """P12: socket peer + Host + Origin (if present). Fail closed."""
    ip = handler.client_address[0]
    ok_ip = ip in ("127.0.0.1", "::1")
    if isinstance(ip, str) and ip.startswith("::ffff:"):
        ok_ip = ip.split(":")[-1] == "127.0.0.1"
    if not ok_ip:
        return False

    host = handler.headers.get("Host", "")
    hn = _parse_host_hostname(host)
    if hn not in ("127.0.0.1", "localhost", "[::1]", "::1"):
        return False

    origin = handler.headers.get("Origin")
    if not origin:
        return True
    o = origin.strip()
    if o in ("null", "file://"):
        return True
    if re.match(
        r"^http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?/?$",
        o,
    ):
        return True
    return False


def _send_json(
    handler: BaseHTTPRequestHandler,
    status: int,
    obj: dict[str, Any],
) -> None:
    raw = json.dumps(obj).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    if not getattr(handler, "_omit_response_body", False):
        handler.wfile.write(raw)


def handle_vault_scan_post(
    handler: BaseHTTPRequestHandler,
    *,
    project_root: Path,
) -> None:
    if not is_localhost_request(handler):
        print(
            "scan rejected non-localhost",
            handler.headers.get("Origin", ""),
            file=sys.stderr,
            flush=True,
        )
        _send_json(
            handler,
            403,
            {"error": "scan_localhost_only"},
        )
        return

    short_id = secrets.token_hex(4)
    try:
        store = get_detection_store()
        cands, sources, _reasons = run_scan(project_root)
        at = _iso_now()
        detections: list[dict[str, Any]] = []
        for c in cands:
            did = store.add_detection(
                c["provider"],
                c["key_value"],
                int(c["key_length"]),
                c["source"],
            )
            detections.append(
                {
                    "detection_id": did,
                    "provider": c["provider"],
                    "source": c["source"],
                    "masked_preview": patterns.masked_preview(
                        c["provider"], c["key_value"]
                    ),
                    "key_length": int(c["key_length"]),
                    "detected_at": at,
                }
            )
        host = handler.headers.get("Host", "")
        rpath = write_vault_scan_receipt(
            sources_scanned=sources,
            detections_found=len(detections),
            host=host,
        )
        if rpath:
            rp = Path(rpath)
            try:
                rel = rp.resolve().relative_to(Path.home().resolve())
                approx = f"~/{rel.as_posix()}"
            except ValueError:
                approx = str(rp)
        else:
            approx = "~/.omnix/receipts/"
        out: dict[str, Any] = {
            "detections": detections,
            "receipt_path": approx,
        }
        _send_json(handler, 200, out)
        # P21: summary only
        print(
            f"vault scan: {len(detections)} detections from {len(sources)} sources",
            flush=True,
        )
    except Exception:
        _send_json(
            handler,
            500,
            {"error": "scan_internal", "id": short_id},
        )


def handle_vault_scan_consume_post(
    handler: BaseHTTPRequestHandler, data: dict[str, Any]
) -> None:
    if not is_localhost_request(handler):
        print(
            "scan consume rejected non-localhost",
            handler.headers.get("Origin", ""),
            file=sys.stderr,
            flush=True,
        )
        _send_json(
            handler,
            403,
            {"error": "scan_localhost_only"},
        )
        return

    did = str(data.get("detection_id", ""))
    if not did:
        _send_json(
            handler,
            404,
            {"ok": False, "error": "detection_not_found_or_expired"},
        )
        return

    store = get_detection_store()
    got = store.pop_detection(did)
    if not got:
        _send_json(
            handler,
            404,
            {"ok": False, "error": "detection_not_found_or_expired"},
        )
        return
    _send_json(
        handler,
        200,
        {
            "ok": True,
            "provider": got["provider"],
            "key": got["key"],
        },
    )
