"""src/fabric/providers/common.py — shared HTTP helpers
Compliance: P11, P17, P20, P23
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

Urlopen = Callable[..., Any]

_urlopen: Urlopen | None = None


def set_urlopen_for_tests(fn: Urlopen | None) -> None:
    global _urlopen
    _urlopen = fn


def _open(req: urllib.request.Request, timeout: float) -> Any:
    fn = _urlopen or urllib.request.urlopen
    return fn(req, timeout=timeout)


def redact_url_for_log(url: str) -> str:
    """P23: never log Google API key query."""
    if "?key=" in url:
        return url.split("?")[0] + "?key=***"
    return url


def is_transient_http_status(code: int) -> bool:
    return code == 429 or code == 529 or code >= 500


def request_json(
    url: str,
    *,
    method: str = "POST",
    headers: dict[str, str],
    body: dict[str, Any] | None,
    timeout_s: float,
) -> tuple[int, Any]:
    """
    Returns (status_code, parsed_json_or_str). Raises URLError on network failure.
    """
    payload: bytes | None = None
    hdrs = dict(headers)
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=payload, method=method, headers=hdrs)
    try:
        with _open(req, timeout_s) as resp:
            status = int(getattr(resp, "status", 200))
            raw = resp.read().decode("utf-8")
            try:
                return status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return status, raw
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8")
        except Exception:
            raw = ""
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw
        return int(e.code), parsed
    except urllib.error.URLError:
        raise
