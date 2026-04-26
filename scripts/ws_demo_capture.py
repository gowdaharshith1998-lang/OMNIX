#!/usr/bin/env python3
"""
Headless WebSocket trace for OMNIX Studio: connect, subscribe, log every message.

Requires a running ``omnix studio`` and the ``websockets`` package.

Example::

  OMNIX_STUDIO_OMNIX_DIR=/tmp/omnix-trace \\
    python3 omnix.py studio /tmp/ws-demo-project &

  python3 scripts/ws_demo_capture.py --project /tmp/ws-demo-project --seconds 30
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any

try:
    import websockets
except ImportError:
    websockets = None  # type: ignore[assignment, misc]


def _jpost(url: str, obj: dict[str, Any], *, timeout: float = 30.0) -> Any:
    data = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _jget(url: str, *, timeout: float = 30.0) -> Any:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _jput(
    url: str, body: dict[str, Any], *, method: str = "PUT", timeout: float = 30.0
) -> None:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        r.read()


def _ws_url(base_http: str, path: str) -> str:
    p = "wss" if base_http.lower().startswith("https") else "ws"
    h = base_http.split("://", 1)[-1].rstrip("/")
    return f"{p}://{h}{path}"


async def _scripted_writes(
    base: str, wid: str, t_write: list[float | None]
) -> None:
    def post_file(rel: str, content: str) -> None:
        b = f"{base.rstrip('/')}/api/workspace/{wid}/file"
        _jpost(b, {"path": rel, "content": content})

    def put_file(rel: str, content: str) -> None:
        g = _jget(
            f"{base.rstrip('/')}/api/workspace/{wid}/file?path="
            f"{urllib.parse.quote(rel, safe='')}"
        )
        m = float(g.get("last_modified", 0.0) or 0.0)
        p = f"{base.rstrip('/')}/api/workspace/{wid}/file"
        _jput(
            p,
            {
                "path": rel,
                "content": content,
                "expected_last_modified": m,
            },
        )

    await asyncio.sleep(1.0)
    t_write.append(time.time())
    post_file(
        "demo.py",
        "def foo():\n    pass\n\ndef bar():\n    return 1\n",
    )
    await asyncio.sleep(3.0)
    t_write.append(time.time())
    put_file(
        "demo.py",
        "def foo():\n    return 0\n\ndef bar():\n    return 2\n\ndef use():\n"
        "    foo(); bar()\n",
    )
    await asyncio.sleep(2.0)
    t_write.append(time.time())
    m = _jget(
        f"{base.rstrip('/')}/api/workspace/{wid}/file?path=demo.py"
    )
    c0 = str(m.get("content", ""))
    put_file(
        "demo.py",
        c0
        + "\n"
        + "class C:\n"
        + "    def m(self) -> None:\n"
        + "        use()\n        foo()\n",
    )


async def _run(
    base: str, project: str, seconds: float, do_writes: bool
) -> int:
    if websockets is None:
        print("Install websockets: pip install websockets", file=sys.stderr)
        return 2

    t_write: list[float | None] = []

    o = _jpost(
        f"{base.rstrip('/')}/api/workspace/open", {"path": project}
    )
    wid: str = o["workspace_id"]
    print(
        json.dumps(
            {
                "phase": "opened",
                "workspace_id": wid,
                "mode": o.get("mode"),
            },
        ),
        flush=True,
    )

    uri = _ws_url(base, f"/ws/workspace/{wid}")
    messages: list[tuple[float, str, dict[str, Any]]] = []

    async with websockets.connect(  # noqa: SIM115
        uri, max_size=None, open_timeout=30, close_timeout=5
    ) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "subscribe",
                    "workspace_id": wid,
                }
            )
        )
        wtask: asyncio.Task[None] | None = None
        if do_writes:
            wtask = asyncio.create_task(
                _scripted_writes(
                    base,
                    wid,
                    t_write,  # noqa: E501
                )
            )

        t_end = time.time() + float(seconds)
        while time.time() < t_end:
            try:
                rem = t_end - time.time()
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.15, rem))
            except (asyncio.TimeoutError, OSError, EOFError):
                if time.time() >= t_end - 0.01:
                    break
                continue
            except websockets.exceptions.ConnectionClosed:
                break
            ts = time.time()
            try:
                o = json.loads(str(raw))  # type: ignore[union-attr, no-untyped-def, misc, no-untyped-def, no-untyped-def, no-any-return]
            except json.JSONDecodeError:  # noqa: E501
                o = {"type": "invalid_json"}
            typ = str(o.get("type", ""))
            messages.append((ts, typ, o))
            print(
                json.dumps(
                    {
                        "t_epoch": round(ts, 3),
                        "type": o.get("type"),  # noqa: E501
                        "raw": o,
                    },
                    default=str,
                )[:8000],  # noqa: E501
                flush=True,
            )

        if wtask is not None:
            wtask.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await wtask

    types_order = [m[1] for m in messages]
    print(  # noqa: E501
        "\n--- summary ---\n"  # noqa: E501
        + json.dumps(  # noqa: E501
            {
                "type_counts": dict(Counter(types_order)),  # noqa: E501
                "type_sequence_head": types_order[:60],
            },
            indent=2,
        ),
        flush=True,
    )
    if t_write and t_write[0] is not None:
        first_t = t_write[0]  # noqa: E501
        first_node = next(
            (
                m[0]  # noqa: E501
                for m in messages
                if m[1] == "node_added" and m[0] >= (first_t or 0)  # noqa: E501
            ),
            None,  # noqa: E501
        )
        if first_node and first_t:
            print(
                f"latency_s echo_to_first_node_after_t0: {first_node - first_t:.3f}"
            )  # noqa: E501
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Capture Studio WebSocket messages (30s demo trace).",
    )
    ap.add_argument(  # noqa: E501
        "--base",
        default="http://127.0.0.1:7778",
        help="Studio HTTP base URL (default: http://127.0.0.1:7778).",
    )
    ap.add_argument(  # noqa: E501
        "--project",
        required=True,
        help="Absolute project directory path to open (must match studio root).",  # noqa: E501
    )
    ap.add_argument(  # noqa: E501
        "--seconds",
        type=float,
        default=30.0,
        help="Read messages for this many seconds (default: 30).",
    )
    ap.add_argument(  # noqa: E501
        "--no-writes",
        action="store_true",
        help="Do not run the scripted file writes (connect only).",
    )
    args = ap.parse_args()  # noqa: E501
    rc = asyncio.run(
        _run(
            args.base,
            args.project,
            args.seconds,
            do_writes=not bool(args.no_writes),  # noqa: E501
        )
    )
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
