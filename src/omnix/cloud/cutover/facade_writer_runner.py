"""Strangler-fig facade writer runner — in-cluster sidecar daemon.

Subscribes to the omnix-api controller's SSE event stream at
``/v1/cutover/events`` and atomically rewrites both
``/etc/envoy/routes/routes.json`` (RDS) and ``/etc/envoy/clusters/clusters.json``
(CDS) on every signed cutover shift. Envoy's filesystem subscription
hot-reloads via mtime polling (~1s detection latency).

Mode (``OMNIX_FACADE_MODE``):

- ``dynamic`` (default): writer drives both files. New units appear in
  Envoy automatically as soon as the controller authorizes a shift for
  them — no helm upgrade required.
- ``static``: chart pre-renders the cluster table; writer only drives
  routes.json. Used for air-gapped / regulated environments.

Bootstrap ordering: this runner is a K8s 1.29+ native sidecar
(``initContainers`` with ``restartPolicy: Always``). It starts BEFORE
the Envoy main container, fetches the controller's initial state via
``GET /v1/cutover/units``, and writes valid routes + clusters files
SYNCHRONOUSLY before the SSE subscribe loop. By the time Envoy boots,
the files exist (or are empty-but-valid if the controller is unreachable
— see ``seed_initial_state``).
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
from omnix.cloud.cutover.facade_writer import (
    FacadeWriter,
    RouteCompositionConfig,
)

log = logging.getLogger("omnix.cloud.cutover.writer_runner")

DEFAULT_CONTROLLER_URL = "http://omnix-api:8080"
SUBSCRIBE_PATH = "/v1/cutover/events"
BOOTSTRAP_PATH = "/v1/cutover/units"
RECONNECT_BACKOFFS = [1, 2, 4, 8, 16, 30]
SEED_RETRY_BACKOFFS = [1, 2, 4]  # 3 attempts before falling back to empty-valid


@dataclass(frozen=True)
class RunnerConfig:
    routes_path: Path
    candidate_template: str         # cluster-name template (used by legacy compute_routes path)
    controller_url: str
    mode: str = "dynamic"           # dynamic | static
    clusters_path: Path | None = None
    legacy_service: str = "legacy.default.svc.cluster.local:80"
    candidate_service_template: str = ""  # DNS template (used by compute_clusters)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RunnerConfig":
        env = env if env is not None else os.environ
        mode = env.get("OMNIX_FACADE_MODE", "dynamic")
        if mode not in ("dynamic", "static"):
            raise ValueError(f"unknown OMNIX_FACADE_MODE: {mode!r}; expected dynamic|static")
        clusters_path = None
        if mode == "dynamic":
            clusters_path = Path(env.get("OMNIX_FACADE_CLUSTERS_PATH",
                                          "/etc/envoy/clusters/clusters.json"))
        return cls(
            routes_path=Path(env.get("OMNIX_FACADE_ROUTES_PATH",
                                       "/etc/envoy/routes/routes.json")),
            candidate_template=env.get("OMNIX_FACADE_CANDIDATE_TEMPLATE",
                                        "candidate_{unit}"),
            controller_url=env.get("OMNIX_CONTROLLER_URL", DEFAULT_CONTROLLER_URL),
            mode=mode,
            clusters_path=clusters_path,
            legacy_service=env.get("OMNIX_LEGACY_SERVICE",
                                    "legacy.default.svc.cluster.local:80"),
            candidate_service_template=env.get("OMNIX_CANDIDATE_SERVICE_TEMPLATE", ""),
        )

    def to_composition_config(self) -> RouteCompositionConfig:
        # When the operator hasn't supplied a DNS-shaped
        # candidate_service_template, fall back to the cluster-name template —
        # compute_clusters tolerates non-DNS hosts (parses with default port).
        candidate_service_template = (
            self.candidate_service_template or self.candidate_template
        )
        return RouteCompositionConfig(
            routes_path=self.routes_path,
            clusters_path=self.clusters_path,
            legacy_service=self.legacy_service,
            candidate_service_template=candidate_service_template,
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
    """Build a CutoverEvent shell from a controller SSE payload."""
    return CutoverEvent(
        event_id=str(payload.get("event_id") or payload.get("receipt_id") or ""),
        tenant_id=str(payload.get("tenant_id", "")),
        unit_id=str(payload["unit_id"]),
        previous_percentage=int(payload.get("previous_percentage", 0)),
        target_percentage=int(payload["target_percentage"]),
        verifier_summary=payload.get("verifier_summary", {}) or {},
    )


async def seed_initial_state(
    client: httpx.AsyncClient,
    cfg: RunnerConfig,
    writer: FacadeWriter,
) -> int:
    """Seed the writer's table from the controller, with retry + fallback.

    Returns the number of units seeded. The two important properties:

    1. **Synchronous**: this completes BEFORE the SSE subscribe loop starts,
       so the K8s 1.29+ native-sidecar ordering guarantee (writer starts
       before Envoy) translates to a guaranteed-valid clusters.json +
       routes.json at the moment Envoy reads them via filesystem
       CDS / RDS.

    2. **Empty-but-valid on failure**: 3 retries (1s/2s/4s backoff). If
       the controller is unreachable, we write empty-but-VALID files.
       Envoy boots cleanly, every request 503s, but the pod is Ready and
       reconcilable. The next SSE event picks up state.

       Without this, Envoy could deadlock cluster_manager init on a
       missing CDS file, leaving the pod permanently un-Ready.
    """
    url = f"{cfg.controller_url}{BOOTSTRAP_PATH}"
    last_err: Exception | None = None
    for attempt, backoff in enumerate(SEED_RETRY_BACKOFFS):
        try:
            r = await client.get(url, timeout=10.0)
            if r.status_code == 404:
                # endpoint not deployed (older controller) — write empty
                # state and let the SSE loop catch us up.
                log.info("seed: %s 404 (controller predates the units endpoint); "
                         "writing empty state", url)
                writer.write_empty()
                return 0
            r.raise_for_status()
            payload = r.json()
            units_data = payload.get("units", []) if isinstance(payload, dict) else payload
            if not isinstance(units_data, list):
                units_data = []
            units: list[tuple[str, int]] = []
            for u in units_data:
                if not isinstance(u, dict) or "unit_id" not in u:
                    continue
                pct = u.get("percentage", u.get("target_percentage", 0))
                units.append((str(u["unit_id"]), int(pct)))
            writer.seed_from_units(units)
            log.info("seed: bootstrapped %d unit(s) from %s", len(units), url)
            return len(units)
        except (httpx.HTTPError, OSError) as e:
            last_err = e
            log.warning("seed attempt %d/%d failed: %s; retrying in %ds",
                        attempt + 1, len(SEED_RETRY_BACKOFFS), e, backoff)
            await asyncio.sleep(backoff)

    log.error("seed: controller unreachable after %d attempts; writing empty-valid "
              "files so Envoy boots cleanly. last_err=%s",
              len(SEED_RETRY_BACKOFFS), last_err)
    writer.write_empty()
    return 0


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
    return FacadeWriter(controller=None, config=cfg.to_composition_config())


async def run(cfg: RunnerConfig | None = None) -> int:
    cfg = cfg if cfg is not None else RunnerConfig.from_env()
    logging.basicConfig(
        level=os.environ.get("OMNIX_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log.info("facade_writer_runner starting; mode=%s routes=%s clusters=%s controller=%s",
             cfg.mode, cfg.routes_path,
             cfg.clusters_path or "<static-mode-skip>",
             cfg.controller_url)
    writer = _build_writer(cfg)
    stop = asyncio.Event()

    def _on_signal(signum, _frame):
        log.info("received signal %s; shutting down", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    last_event_id: list[str | None] = [None]
    async with httpx.AsyncClient() as client:
        # CRITICAL: seed synchronously BEFORE the SSE loop. Envoy will start
        # reading our filesystem CDS/RDS as soon as the native sidecar
        # transitions to Started — those files must exist by then.
        await seed_initial_state(client, cfg, writer)

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
