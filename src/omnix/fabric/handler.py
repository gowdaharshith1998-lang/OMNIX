"""src/fabric/handler.py — HTTP routes for Provider Fabric
Compliance: P11, P12, P13
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler
from typing import Any

from omnix.fabric.config import load_config
from omnix.fabric.dispatcher import dispatch, status_snapshot
from omnix.fabric.spend import spend_snapshot
from omnix.fabric.telemetry import recent
from omnix.scan.handler import is_localhost_request

_EXEC: ThreadPoolExecutor | None = None


def _executor() -> ThreadPoolExecutor:
    global _EXEC
    if _EXEC is None:
        cfg = load_config()
        n = max(1, int(cfg.get("max_concurrent_dispatches", 4)))
        _EXEC = ThreadPoolExecutor(max_workers=n)
    return _EXEC


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


def handle_fabric_dispatch_post(
    handler: BaseHTTPRequestHandler,
    data: dict[str, Any],
) -> None:
    if not is_localhost_request(handler):
        print(
            "fabric dispatch rejected non-localhost",
            handler.headers.get("Origin", ""),
            file=sys.stderr,
            flush=True,
        )
        _send_json(
            handler,
            403,
            {"ok": False, "error": "dispatch_localhost_only"},
        )
        return
    opts = data.get("options") if isinstance(data.get("options"), dict) else {}
    timeout_ms = int(opts.get("timeout_ms", 30000))
    pool_timeout = max(60.0, timeout_ms / 1000.0 + 45.0)
    try:
        result = _executor().submit(dispatch, data).result(timeout=pool_timeout)
    except ValueError as e:
        _send_json(
            handler,
            400,
            {"ok": False, "error": "bad_request", "detail": str(e)},
        )
        return
    except Exception as e:
        print("fabric dispatch internal error", type(e).__name__, file=sys.stderr, flush=True)
        _send_json(
            handler,
            500,
            {"ok": False, "error": "internal_error"},
        )
        return

    http_status = 200
    if not result.get("ok") and result.get("error") in (
        "provider_error",
        "exhausted_retries",
    ):
        http_status = 502
    _send_json(handler, http_status, result)


def handle_fabric_status_get(handler: BaseHTTPRequestHandler) -> None:
    if not is_localhost_request(handler):
        _send_json(
            handler,
            403,
            {"ok": False, "error": "dispatch_localhost_only"},
        )
        return
    _send_json(handler, 200, status_snapshot())


def handle_fabric_telemetry_get(handler: BaseHTTPRequestHandler) -> None:
    if not is_localhost_request(handler):
        _send_json(
            handler,
            403,
            {"ok": False, "error": "dispatch_localhost_only"},
        )
        return
    _send_json(handler, 200, {"entries": recent()})


def handle_fabric_spend_get(handler: BaseHTTPRequestHandler) -> None:
    if not is_localhost_request(handler):
        _send_json(
            handler,
            403,
            {"ok": False, "error": "dispatch_localhost_only"},
        )
        return
    _send_json(handler, 200, spend_snapshot(load_config()))


def reset_executor_for_tests() -> None:
    global _EXEC
    if _EXEC is not None:
        _EXEC.shutdown(wait=False)
        _EXEC = None
