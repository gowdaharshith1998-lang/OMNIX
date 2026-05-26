"""Tests for the strangler-fig facade writer runner.

These tests exercise the parsing/event-application surface directly and use
``respx`` (already a dev dependency via httpx) for HTTP mocking on the
bootstrap + SSE paths.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from omnix.cloud.cutover.facade_controller import CutoverEvent
from omnix.cloud.cutover.facade_writer import FacadeWriter
from omnix.cloud.cutover.facade_writer_runner import (
    BOOTSTRAP_PATH,
    SUBSCRIBE_PATH,
    RunnerConfig,
    apply_event_from_payload,
    bootstrap,
    consume_stream,
    make_event,
    parse_sse_frame,
)


# -------------------- parse_sse_frame --------------------


def test_parse_sse_frame_simple_event():
    frame = parse_sse_frame(["id: 42", "event: cutover-shift", "data: {\"x\":1}"])
    assert frame == {"id": "42", "event": "cutover-shift", "data": '{"x":1}'}


def test_parse_sse_frame_multiline_data_joined_with_newline():
    frame = parse_sse_frame(["data: line-one", "data: line-two"])
    assert frame["data"] == "line-one\nline-two"


def test_parse_sse_frame_comment_lines_ignored():
    # Lines beginning with ':' are SSE comments; many servers use them as
    # keepalive pings between real events.
    frame = parse_sse_frame([": keepalive", "id: 7", ":ping", "data: hi"])
    assert frame == {"id": "7", "data": "hi"}


def test_parse_sse_frame_empty_input_returns_empty_dict():
    assert parse_sse_frame([]) == {}
    assert parse_sse_frame([":only-comment"]) == {}


def test_parse_sse_frame_field_without_colon():
    # Per spec a line without ':' is a field name with empty value.
    frame = parse_sse_frame(["retry"])
    assert frame == {"retry": ""}


# -------------------- RunnerConfig.from_env --------------------


def test_runner_config_from_env_defaults():
    cfg = RunnerConfig.from_env({})
    assert cfg.routes_path == Path("/etc/envoy/routes/routes.json")
    assert cfg.candidate_template == "candidate_{unit}"
    assert cfg.controller_url == "http://omnix-api:8080"


def test_runner_config_from_env_overrides():
    cfg = RunnerConfig.from_env({
        "OMNIX_FACADE_ROUTES_PATH": "/tmp/routes.json",
        "OMNIX_FACADE_CANDIDATE_TEMPLATE": "cand-{unit}.svc",
        "OMNIX_CONTROLLER_URL": "http://api.omnix.local:9000",
    })
    assert cfg.routes_path == Path("/tmp/routes.json")
    assert cfg.candidate_template == "cand-{unit}.svc"
    assert cfg.controller_url == "http://api.omnix.local:9000"


# -------------------- make_event --------------------


def test_make_event_from_payload_minimal():
    event = make_event({"unit_id": "calc", "target_percentage": 25})
    assert isinstance(event, CutoverEvent)
    assert event.unit_id == "calc"
    assert event.target_percentage == 25
    assert event.tenant_id == ""
    assert event.event_id == ""


def test_make_event_from_payload_full():
    event = make_event({
        "event_id": "ev-1",
        "tenant_id": "acme",
        "unit_id": "checkout",
        "previous_percentage": 0,
        "target_percentage": 10,
        "verifier_summary": {"scientist_mismatches": 0},
    })
    assert event.event_id == "ev-1"
    assert event.tenant_id == "acme"
    assert event.previous_percentage == 0
    assert event.target_percentage == 10
    assert event.verifier_summary == {"scientist_mismatches": 0}


def test_make_event_coerces_string_percentages_to_int():
    event = make_event({"unit_id": "u", "target_percentage": "33"})
    assert event.target_percentage == 33


# -------------------- apply_event_from_payload (real writer + tmp_path) --------------------


def _make_writer(tmp_path: Path) -> FacadeWriter:
    return FacadeWriter(
        controller=None,  # type: ignore[arg-type]
        routes_path=tmp_path / "routes.json",
        candidate_template="candidate_{unit}",
    )


def test_apply_event_from_payload_writes_routes_json(tmp_path):
    writer = _make_writer(tmp_path)
    apply_event_from_payload(writer, {
        "unit_id": "calc", "target_percentage": 25, "tenant_id": "t",
    })
    routes_file = tmp_path / "routes.json"
    assert routes_file.exists()
    doc = json.loads(routes_file.read_text())
    weighted = doc["resources"][0]["virtual_hosts"][0]["routes"][0]["route"]["weighted_clusters"]
    weights = {c["name"]: c["weight"] for c in weighted["clusters"]}
    assert weights["legacy_calc"] == 75
    assert weights["candidate_calc"] == 25


def test_apply_event_from_payload_atomic_no_torn_writes(tmp_path):
    # Run several updates back-to-back; final state must match the last one.
    writer = _make_writer(tmp_path)
    for pct in (10, 35, 50, 100):
        apply_event_from_payload(writer, {"unit_id": "u", "target_percentage": pct})
    doc = json.loads((tmp_path / "routes.json").read_text())
    weights = {c["name"]: c["weight"] for c in
               doc["resources"][0]["virtual_hosts"][0]["routes"][0]["route"]
               ["weighted_clusters"]["clusters"]}
    assert weights["candidate_u"] == 100
    assert weights["legacy_u"] == 0


# -------------------- bootstrap (mocked HTTP) --------------------


def _build_async_client(handler) -> httpx.AsyncClient:
    """Build an httpx.AsyncClient backed by an in-process MockTransport."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_bootstrap_handles_404_gracefully(tmp_path):
    cfg = RunnerConfig.from_env({"OMNIX_CONTROLLER_URL": "http://ctl"})
    writer = _make_writer(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == BOOTSTRAP_PATH
        return httpx.Response(404, json={"detail": "not deployed"})

    async with _build_async_client(handler) as client:
        seeded = await bootstrap(client, cfg, writer)
    assert seeded == 0
    assert not (tmp_path / "routes.json").exists()


@pytest.mark.asyncio
async def test_bootstrap_seeds_units_from_controller(tmp_path):
    cfg = RunnerConfig.from_env({"OMNIX_CONTROLLER_URL": "http://ctl"})
    writer = _make_writer(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"units": [
            {"unit_id": "u1", "tenant_id": "acme", "percentage": 5},
            {"unit_id": "u2", "tenant_id": "acme", "percentage": 40},
        ]})

    async with _build_async_client(handler) as client:
        seeded = await bootstrap(client, cfg, writer)
    assert seeded == 2
    doc = json.loads((tmp_path / "routes.json").read_text())
    weights = {}
    for vhost in doc["resources"][0]["virtual_hosts"]:
        for cluster in vhost["routes"][0]["route"]["weighted_clusters"]["clusters"]:
            weights[cluster["name"]] = cluster["weight"]
    assert weights["candidate_u1"] == 5
    assert weights["candidate_u2"] == 40


@pytest.mark.asyncio
async def test_bootstrap_swallows_transport_errors(tmp_path):
    cfg = RunnerConfig.from_env({"OMNIX_CONTROLLER_URL": "http://ctl"})
    writer = _make_writer(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    async with _build_async_client(handler) as client:
        seeded = await bootstrap(client, cfg, writer)
    assert seeded == 0


# -------------------- consume_stream (mocked SSE bytes) --------------------


class _FakeSSEResponse:
    """Minimal stand-in for an httpx streaming response used by consume_stream."""

    def __init__(self, frames_text: str, status_code: int = 200) -> None:
        self._text = frames_text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)

    async def aiter_lines(self):
        # Yield lines exactly the way httpx does — without trailing newlines.
        for line in self._text.split("\n"):
            yield line


class _FakeStreamContext:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *_a):
        return None


class _FakeClient:
    """Single-purpose client whose stream() returns canned SSE bytes."""

    def __init__(self, response):
        self._response = response
        self.last_request_headers: dict | None = None

    def stream(self, method, url, headers=None, timeout=None):
        self.last_request_headers = dict(headers or {})
        return _FakeStreamContext(self._response)


@pytest.mark.asyncio
async def test_consume_stream_applies_one_shift_event(tmp_path):
    cfg = RunnerConfig.from_env({})
    writer = _make_writer(tmp_path)
    frames = (
        "id: 1\n"
        "event: cutover-shift\n"
        'data: {"unit_id": "calc", "target_percentage": 25, "tenant_id": "t"}\n'
        "\n"  # end of frame (blank line)
    )
    client = _FakeClient(_FakeSSEResponse(frames))
    last_id = [None]
    stop = asyncio.Event()

    async def stop_soon():
        # Let consume_stream process the frame then close the iterator.
        await asyncio.sleep(0.05)
        stop.set()

    asyncio.create_task(stop_soon())
    # consume_stream returns when stop is set OR aiter_lines exhausts
    await consume_stream(client, cfg, writer, last_id, stop)  # type: ignore[arg-type]
    assert last_id[0] == "1"
    doc = json.loads((tmp_path / "routes.json").read_text())
    weights = {c["name"]: c["weight"]
               for c in doc["resources"][0]["virtual_hosts"][0]["routes"][0]
               ["route"]["weighted_clusters"]["clusters"]}
    assert weights["candidate_calc"] == 25


@pytest.mark.asyncio
async def test_consume_stream_skips_keepalive_frames(tmp_path):
    cfg = RunnerConfig.from_env({})
    writer = _make_writer(tmp_path)
    frames = (
        "event: keepalive\n"
        "data: {}\n"
        "\n"
    )
    client = _FakeClient(_FakeSSEResponse(frames))
    last_id = [None]
    stop = asyncio.Event()
    asyncio.create_task(_set_after(stop, 0.05))
    await consume_stream(client, cfg, writer, last_id, stop)  # type: ignore[arg-type]
    # No real event => no routes.json written.
    assert not (tmp_path / "routes.json").exists()


@pytest.mark.asyncio
async def test_consume_stream_swallows_malformed_json(tmp_path):
    cfg = RunnerConfig.from_env({})
    writer = _make_writer(tmp_path)
    frames = (
        "id: 5\n"
        "data: { not-json\n"
        "\n"
        "id: 6\n"
        'data: {"unit_id": "u", "target_percentage": 50}\n'
        "\n"
    )
    client = _FakeClient(_FakeSSEResponse(frames))
    last_id = [None]
    stop = asyncio.Event()
    asyncio.create_task(_set_after(stop, 0.05))
    await consume_stream(client, cfg, writer, last_id, stop)  # type: ignore[arg-type]
    # Second frame is well-formed; first is dropped without crashing.
    assert (tmp_path / "routes.json").exists()
    doc = json.loads((tmp_path / "routes.json").read_text())
    weights = {c["name"]: c["weight"]
               for c in doc["resources"][0]["virtual_hosts"][0]["routes"][0]
               ["route"]["weighted_clusters"]["clusters"]}
    assert weights["candidate_u"] == 50
    assert last_id[0] == "6"


@pytest.mark.asyncio
async def test_consume_stream_sends_last_event_id_on_reconnect(tmp_path):
    cfg = RunnerConfig.from_env({})
    writer = _make_writer(tmp_path)
    client = _FakeClient(_FakeSSEResponse(""))  # empty stream
    last_id = ["abc123"]
    stop = asyncio.Event()
    stop.set()  # immediate exit
    await consume_stream(client, cfg, writer, last_id, stop)  # type: ignore[arg-type]
    assert client.last_request_headers is not None
    assert client.last_request_headers.get("Last-Event-ID") == "abc123"


async def _set_after(event: asyncio.Event, delay: float) -> None:
    await asyncio.sleep(delay)
    event.set()


# -------------------- module/endpoint constants --------------------


def test_paths_are_versioned_v1():
    assert SUBSCRIBE_PATH.startswith("/v1/")
    assert BOOTSTRAP_PATH.startswith("/v1/")
