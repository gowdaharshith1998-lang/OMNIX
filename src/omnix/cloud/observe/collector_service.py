"""Observation collector service.

In-cluster sink that the Tetragon DaemonSet forwarder + Debezium consumers +
mainframe bridges POST to. Parses each delivery via the existing pure parsers
in this package and writes the resulting Observation rows to the configured
sink (in-memory for tests, Redis stream for production).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Iterable

from fastapi import FastAPI, Request, Response

from omnix.cloud.observe.cdc_collector import collect_cdc
from omnix.cloud.observe.envelope import (
    InMemorySink,
    Observation,
    ObservationSink,
)
from omnix.cloud.observe.mainframe_collector import (
    collect_cics,
    collect_smf,
    collect_vsam,
)
from omnix.cloud.observe.tetragon_collector import collect_events

logger = logging.getLogger("omnix.collector_service")


def _load_filter(path: str | None) -> dict:
    if not path or not os.path.exists(path):
        return {}
    try:
        return json.loads(open(path, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError):
        logger.warning("collector_service: could not read filter at %s", path)
        return {}


def _is_allowed_namespace(event: dict, allow: list[str]) -> bool:
    if not allow:
        return True
    ns = event.get("namespace") or event.get("pod", {}).get("namespace")
    return not ns or ns in allow


def _iter_jsonl(body: bytes) -> Iterable[dict]:
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def build_app(sink: ObservationSink | None = None, *, filter_path: str | None = None) -> FastAPI:
    """Construct the collector FastAPI app. Sink + filter are injectable for tests."""
    app = FastAPI(title="omnix-collector", version="0.6.1")
    app.state.sink = sink or InMemorySink()
    app.state.filter = _load_filter(filter_path)
    app.state.counters: dict[str, int] = {
        "tetragon_received": 0,
        "tetragon_filtered": 0,
        "cdc_received": 0,
        "mainframe_received": 0,
    }

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True}

    @app.get("/metrics")
    async def metrics() -> Response:
        # Minimal Prometheus exposition; the operator's metrics-mesh handles
        # full instrumentation. We just publish counters.
        lines = []
        for k, v in app.state.counters.items():
            lines.append(f"omnix_collector_{k} {v}")
        return Response("\n".join(lines) + "\n", media_type="text/plain")

    @app.post("/v1/observe/tetragon")
    async def ingest_tetragon(request: Request) -> dict:
        body = await request.body()
        allow = app.state.filter.get("namespace_allow_list", [])
        events: list[dict] = []
        for ev in _iter_jsonl(body):
            app.state.counters["tetragon_received"] += 1
            if not _is_allowed_namespace(ev, allow):
                app.state.counters["tetragon_filtered"] += 1
                continue
            events.append(ev)
        collect_events(events, sink=app.state.sink, require_label=False)
        return {"accepted": len(events)}

    @app.post("/v1/observe/cdc")
    async def ingest_cdc(request: Request) -> dict:
        body = await request.body()
        events = list(_iter_jsonl(body))
        app.state.counters["cdc_received"] += len(events)
        collect_cdc(events, sink=app.state.sink)
        return {"accepted": len(events)}

    @app.post("/v1/observe/mainframe")
    async def ingest_mainframe(request: Request) -> dict:
        body = await request.body()
        vendor = request.headers.get("x-omnix-vendor", "").lower()
        events = list(_iter_jsonl(body))
        app.state.counters["mainframe_received"] += len(events)
        if vendor == "ironstream":
            collect_smf(events, sink=app.state.sink)
        elif vendor == "tcvision":
            collect_vsam(events, sink=app.state.sink)
        elif vendor == "cprof":
            collect_cics(events, sink=app.state.sink)
        else:
            # Unrouted vendor — drop, but count for ops visibility.
            return {"accepted": 0, "reason": f"unknown vendor: {vendor!r}"}
        return {"accepted": len(events)}

    return app


def _build_sink_from_env() -> ObservationSink:
    sink_kind = os.environ.get("OMNIX_OBSERVE_SINK", "memory").lower()
    if sink_kind == "memory":
        return InMemorySink()
    if sink_kind == "stdout":
        return _StdoutSink()
    if sink_kind == "redis":
        # Lazy import: redis only required for the production sink path.
        try:
            import redis  # type: ignore[import-not-found]
        except ImportError as exc:
            raise SystemExit("OMNIX_OBSERVE_SINK=redis but redis client not installed") from exc
        url = os.environ.get("OMNIX_OBSERVE_REDIS_URL", "redis://localhost:6379/0")
        return _RedisStreamSink(redis.Redis.from_url(url))
    raise SystemExit(f"unsupported OMNIX_OBSERVE_SINK={sink_kind!r}")


class _StdoutSink:
    """Sink that logs each Observation to stdout — used for ops debugging."""

    def absorb(self, obs: Observation) -> None:
        print(json.dumps({
            "kind": obs.kind.value,
            "pod": obs.pod,
            "service": obs.service,
            "redacted": list(obs.redacted_fields),
        }))

    def drain(self) -> list[Observation]:
        return []


class _RedisStreamSink:
    """Production sink — Redis Streams keyed by observation kind."""

    def __init__(self, client) -> None:
        self._client = client

    def absorb(self, obs: Observation) -> None:
        self._client.xadd(
            f"omnix:observe:{obs.kind.value}",
            {
                "service": obs.service or "",
                "pod": obs.pod or "",
                "payload": json.dumps(obs.payload, default=str),
            },
            maxlen=100_000,
            approximate=True,
        )

    def drain(self) -> list[Observation]:
        return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omnix.cloud.observe.collector_service")
    parser.add_argument("--bind", default="0.0.0.0:9050")
    args = parser.parse_args(argv)

    host, port = args.bind.rsplit(":", 1)
    sink = _build_sink_from_env()
    filter_path = os.environ.get("OMNIX_FILTER_PATH")
    app = build_app(sink=sink, filter_path=filter_path)

    try:
        import uvicorn  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("uvicorn required to run collector_service") from exc

    uvicorn.run(app, host=host, port=int(port), log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
