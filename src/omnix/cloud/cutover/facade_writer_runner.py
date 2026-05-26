"""Strangler-fig facade writer runner — in-cluster sidecar daemon.

Subscribes to the omnix-api controller's SSE event stream at
``/v1/cutover/events`` and atomically rewrites
``/etc/envoy/routes/routes.json`` on every signed cutover shift. Envoy's
filesystem RDS picks up the new file via mtime polling (~1s).

Why a sidecar (not in-process): the controller can run on multiple replicas
but the writer must be co-located with Envoy so a torn write cannot happen
across pods. One writer per facade pod, fed by cross-pod SSE broadcast.

Environment variables:
  OMNIX_FACADE_ROUTES_PATH         (default /etc/envoy/routes/routes.json)
  OMNIX_FACADE_CANDIDATE_TEMPLATE  (default candidate_{unit})
  OMNIX_CONTROLLER_URL             (default http://omnix-api:8080)
  OMNIX_LOG_LEVEL                  (default INFO)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import httpx

from omnix.cloud.cutover.facade_controller import CutoverEvent
from omnix.cloud.cutover.facade_writer import FacadeWriter

log = logging.getLogger("omnix.cloud.cutover.writer_runner")

DEFAULT_CONTROLLER_URL = "http://omnix-api:8080"
SUBSCRIBE_PATH = "/v1/cutover/events"
BOOTSTRAP_PATH = "/v1/cutover/units"
RECONNECT_BACKOFFS = [1, 2, 4, 8, 16, 30]


@dataclass(frozen=True)
class RunnerConfig:
    routes_path: Path
    candidate_template: str
    controller_url: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RunnerConfig":
        env = env if env is not None else os.environ
        return cls(
            routes_path=Path(env.get("OMNIX_FACADE_ROUTES_PATH",
                                       "/etc/envoy/routes/routes.json")),
            candidate_template=env.get("OMNIX_FACADE_CANDIDATE_TEMPLATE",
                                        "candidate_{unit}"),
            controller_url=env.get("OMNIX_CONTROLLER_URL", DEFAULT_CONTROLLER_URL),
        )


def parse_sse_frame(lines: list[str]) -> dict[str, str]:
    """Parse a single SSE event frame per the WHATWG spec.

    - Lines beginning with ':' are comments (used as keepalives) and ignored.
    - Each line is ``field[: value]``; the leading space after ':' is stripped.
    - Repeated fields concatenate with newline (per spec, primarily ``data``).
    """
    frame: dict[str, str] = {}
    for line in lines:
        if not line or line.startswith(":"):
            continue
        if ":" not in line:
            field, value = line, ""
        else:
            field, _, value = line.partition(":")
            if value.startswith(" "):
                value = value[1:]
        if field in frame:
            frame[field] = frame[field] + "\n" + value
        else:
            frame[field] = value
    return frame


def make_event(payload: dict) -> CutoverEvent:
    """Build a CutoverEvent shell from a controller SSE payload.

    Only the fields FacadeWriter.apply_event reads are populated. Signature /
    public-key bytes are not needed at the data plane — the controller has
    already authorized this shift.
    """
    return CutoverEvent(
        event_id=str(payload.get("event_id") or payload.get("receipt_id") or ""),
        tenant_id=str(payload.get("tenant_id", "")),
        unit_id=str(payload["unit_id"]),
        previous_percentage=int(payload.get("previous_percentage", 0)),
        target_percentage=int(payload["target_percentage"]),
        verifier_summary=payload.get("verifier_summary", {}) or {},
    )


async def bootstrap(client: httpx.AsyncClient, cfg: RunnerConfig,
                    writer: FacadeWriter) -> int:
    """Seed routes.json from the controller's current state, best-effort.

    A 404 or transport error returns silently — the first live SSE event will
    catch the runner up. Returns the number of units seeded.
    """
    url = f"{cfg.controller_url}{BOOTSTRAP_PATH}"
    try:
        r = await client.get(url, timeout=10.0)
    except (httpx.HTTPError, OSError) as e:
        log.info("bootstrap: %s unreachable (%s); will rely on SSE",
                 url, type(e).__name__)
        return 0
    if r.status_code == 404:
        log.info("bootstrap: %s not deployed yet (404); will rely on SSE", url)
        return 0
    if r.status_code != 200:
        log.warning("bootstrap: %s returned %d; continuing", url, r.status_code)
        return 0
    payload = r.json()
    units = payload.get("units", []) if isinstance(payload, dict) else payload
    if not isinstance(units, list):
        return 0
    seeded = 0
    for u in units:
        if not isinstance(u, dict) or "unit_id" not in u:
            continue
        target = u.get("percentage", u.get("target_percentage", 0))
        writer.apply_event(CutoverEvent(
            event_id=f"bootstrap-{u['unit_id']}",
            tenant_id=str(u.get("tenant_id", "")),
            unit_id=str(u["unit_id"]),
            previous_percentage=0,
            target_percentage=int(target),
            verifier_summary={},
        ))
        seeded += 1
    log.info("bootstrap: seeded %d unit(s)", seeded)
    return seeded


def apply_event_from_payload(writer: FacadeWriter, payload: dict) -> CutoverEvent:
    event = make_event(payload)
    writer.apply_event(event)
    log.info("applied shift tenant=%s unit=%s pct=%s",
             event.tenant_id, event.unit_id, event.target_percentage)
    return event


async def consume_stream(
    client: httpx.AsyncClient,
    cfg: RunnerConfig,
    writer: FacadeWriter,
    last_event_id_holder: list[str | None],
    stop: asyncio.Event,
) -> None:
    """Consume SSE frames until the server closes or ``stop`` is set."""
    headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}
    if last_event_id_holder[0]:
        headers["Last-Event-ID"] = last_event_id_holder[0]
    url = f"{cfg.controller_url}{SUBSCRIBE_PATH}"
    log.info("subscribing to SSE %s (Last-Event-ID=%s)", url,
             last_event_id_holder[0] or "<none>")
    async with client.stream(
        "GET", url, headers=headers,
        timeout=httpx.Timeout(None, connect=10.0),
    ) as r:
        r.raise_for_status()
        frame_lines: list[str] = []
        async for line in r.aiter_lines():
            if stop.is_set():
                return
            if line == "":
                frame = parse_sse_frame(frame_lines)
                frame_lines = []
                if not frame:
                    continue
                if frame.get("event") == "keepalive":
                    continue
                if "id" in frame:
                    last_event_id_holder[0] = frame["id"]
                data = frame.get("data")
                if not data:
                    continue
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    log.warning("malformed SSE data (not JSON): %r", data[:120])
                    continue
                try:
                    apply_event_from_payload(writer, payload)
                except KeyError as e:
                    log.warning("SSE payload missing required field %s: %r", e, payload)
                except Exception:  # noqa: BLE001
                    log.exception("failed to apply SSE event")
            else:
                frame_lines.append(line)


def _build_writer(cfg: RunnerConfig) -> FacadeWriter:
    """FacadeWriter requires a controller for ``seed_from_controller`` only.

    The runner seeds via HTTP, so passing None is safe — apply_event itself
    never touches self._controller.
    """
    return FacadeWriter(
        controller=None,  # type: ignore[arg-type]
        routes_path=cfg.routes_path,
        candidate_template=cfg.candidate_template,
    )


async def run(cfg: RunnerConfig | None = None) -> int:
    cfg = cfg if cfg is not None else RunnerConfig.from_env()
    logging.basicConfig(
        level=os.environ.get("OMNIX_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log.info("facade_writer_runner starting; routes=%s controller=%s",
             cfg.routes_path, cfg.controller_url)
    writer = _build_writer(cfg)
    stop = asyncio.Event()

    def _on_signal(signum, _frame):
        log.info("received signal %s; shutting down", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    last_event_id: list[str | None] = [None]
    async with httpx.AsyncClient() as client:
        await bootstrap(client, cfg, writer)

        attempt = 0
        while not stop.is_set():
            backoff = RECONNECT_BACKOFFS[min(attempt, len(RECONNECT_BACKOFFS) - 1)]
            try:
                await consume_stream(client, cfg, writer, last_event_id, stop)
                if stop.is_set():
                    break
                log.warning("SSE stream closed cleanly; reconnecting in %ds", backoff)
            except httpx.HTTPError as e:
                log.warning("SSE error: %s; reconnecting in %ds", e, backoff)
            except Exception:  # noqa: BLE001
                log.exception("unexpected runner error; reconnecting in %ds", backoff)
            for _ in range(int(backoff * 10)):
                if stop.is_set():
                    break
                await asyncio.sleep(0.1)
            attempt += 1
    log.info("facade_writer_runner exited cleanly")
    return 0


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
