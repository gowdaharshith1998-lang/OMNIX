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
    consume_stream,
    make_event,
    parse_sse_frame,
    seed_initial_state,
)

# Issue #53 dispatch P3 renamed bootstrap → seed_initial_state.
# Keep the old name as a local alias so the existing test names still
# read correctly (test_bootstrap_*) until renamed.
bootstrap = seed_initial_state


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
async def test_bootstrap_handles_404_by_writing_empty_valid_files(tmp_path):
    """Issue #53 P3: 404 on the bootstrap endpoint means the controller
    predates the /v1/cutover/units API. The runner writes empty-but-valid
    routes.json + clusters.json so Envoy boots cleanly (with zero clusters,
    serving 503 for every request) instead of deadlocking on a missing CDS
    file. The SSE loop picks up state when events flow.
    """
    cfg = RunnerConfig.from_env({"OMNIX_CONTROLLER_URL": "http://ctl"})
    writer = _make_writer(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == BOOTSTRAP_PATH
        return httpx.Response(404, json={"detail": "not deployed"})

    async with _build_async_client(handler) as client:
        seeded = await bootstrap(client, cfg, writer)
    assert seeded == 0
    # Empty-but-valid files exist
    assert (tmp_path / "routes.json").exists()
    routes_doc = json.loads((tmp_path / "routes.json").read_text())
    assert routes_doc["resources"][0]["virtual_hosts"] == []


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
    """All retries fail → empty-but-valid files. With 1s/2s/4s backoffs,
    we override to instant so the test runs fast.
    """
    cfg = RunnerConfig.from_env({"OMNIX_CONTROLLER_URL": "http://ctl"})
    writer = _make_writer(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    import omnix.cloud.cutover.facade_writer_runner as runner_mod
    original = runner_mod.SEED_RETRY_BACKOFFS
    runner_mod.SEED_RETRY_BACKOFFS = [0, 0, 0]
    try:
        async with _build_async_client(handler) as client:
            seeded = await bootstrap(client, cfg, writer)
    finally:
        runner_mod.SEED_RETRY_BACKOFFS = original
    assert seeded == 0
    # Empty-but-valid files exist so Envoy boots without deadlock
    assert (tmp_path / "routes.json").exists()


@pytest.mark.asyncio
async def test_seed_dynamic_mode_writes_both_files(tmp_path):
    """In dynamic mode the seed writes BOTH routes.json AND clusters.json."""
    cfg = RunnerConfig.from_env({
        "OMNIX_CONTROLLER_URL": "http://ctl",
        "OMNIX_FACADE_MODE": "dynamic",
        "OMNIX_FACADE_ROUTES_PATH": str(tmp_path / "routes.json"),
        "OMNIX_FACADE_CLUSTERS_PATH": str(tmp_path / "clusters.json"),
        "OMNIX_LEGACY_SERVICE": "legacy.svc:80",
        "OMNIX_CANDIDATE_SERVICE_TEMPLATE": "cand-{unit}.svc:80",
    })
    from omnix.cloud.cutover.facade_writer import FacadeWriter
    writer = FacadeWriter(controller=None, config=cfg.to_composition_config())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"units": [
            {"unit_id": "calc", "percentage": 25},
            {"unit_id": "pay", "percentage": 50},
        ]})

    async with _build_async_client(handler) as client:
        seeded = await seed_initial_state(client, cfg, writer)
    assert seeded == 2
    # Both files written
    assert (tmp_path / "routes.json").exists()
    assert (tmp_path / "clusters.json").exists()
    # Cluster names match the route references
    clusters_doc = json.loads((tmp_path / "clusters.json").read_text())
    cluster_names = {c["name"] for c in clusters_doc["resources"]}
    assert cluster_names == {"legacy_calc", "candidate_calc", "legacy_pay", "candidate_pay"}


@pytest.mark.asyncio
async def test_seed_static_mode_does_not_write_clusters_file(tmp_path):
    """In static mode the writer only writes routes.json — chart pre-renders clusters."""
    cfg = RunnerConfig.from_env({
        "OMNIX_CONTROLLER_URL": "http://ctl",
        "OMNIX_FACADE_MODE": "static",
        "OMNIX_FACADE_ROUTES_PATH": str(tmp_path / "routes.json"),
    })
    assert cfg.clusters_path is None
    from omnix.cloud.cutover.facade_writer import FacadeWriter
    writer = FacadeWriter(controller=None, config=cfg.to_composition_config())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"units": [{"unit_id": "calc", "percentage": 25}]})

    async with _build_async_client(handler) as client:
        await seed_initial_state(client, cfg, writer)
    assert (tmp_path / "routes.json").exists()
    assert not (tmp_path / "clusters.json").exists()


@pytest.mark.asyncio
async def test_seed_succeeds_after_transient_failures(tmp_path):
    """First 2 calls fail with 503; third succeeds. Confirms retry path."""
    cfg = RunnerConfig.from_env({
        "OMNIX_CONTROLLER_URL": "http://ctl",
        "OMNIX_FACADE_ROUTES_PATH": str(tmp_path / "routes.json"),
        "OMNIX_FACADE_CLUSTERS_PATH": str(tmp_path / "clusters.json"),
        "OMNIX_LEGACY_SERVICE": "legacy.svc:80",
        "OMNIX_CANDIDATE_SERVICE_TEMPLATE": "cand-{unit}.svc:80",
    })
    from omnix.cloud.cutover.facade_writer import FacadeWriter
    writer = FacadeWriter(controller=None, config=cfg.to_composition_config())

    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        if call_count[0] <= 2:
            return httpx.Response(503, json={"detail": "transient"})
        return httpx.Response(200, json={"units": [{"unit_id": "calc", "percentage": 10}]})

    import omnix.cloud.cutover.facade_writer_runner as runner_mod
    original = runner_mod.SEED_RETRY_BACKOFFS
    runner_mod.SEED_RETRY_BACKOFFS = [0, 0, 0]  # instant retries
    try:
        async with _build_async_client(handler) as client:
            seeded = await seed_initial_state(client, cfg, writer)
    finally:
        runner_mod.SEED_RETRY_BACKOFFS = original
    assert seeded == 1
    assert call_count[0] == 3


@pytest.mark.asyncio
async def test_seed_writes_empty_clusters_when_controller_unreachable(tmp_path):
    """All 3 retries fail → empty clusters.json written so Envoy boots clean."""
    cfg = RunnerConfig.from_env({
        "OMNIX_CONTROLLER_URL": "http://ctl",
        "OMNIX_FACADE_ROUTES_PATH": str(tmp_path / "routes.json"),
        "OMNIX_FACADE_CLUSTERS_PATH": str(tmp_path / "clusters.json"),
        "OMNIX_LEGACY_SERVICE": "legacy.svc:80",
        "OMNIX_CANDIDATE_SERVICE_TEMPLATE": "cand-{unit}.svc:80",
    })
    from omnix.cloud.cutover.facade_writer import FacadeWriter
    writer = FacadeWriter(controller=None, config=cfg.to_composition_config())

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("controller unreachable")

    import omnix.cloud.cutover.facade_writer_runner as runner_mod
    original = runner_mod.SEED_RETRY_BACKOFFS
    runner_mod.SEED_RETRY_BACKOFFS = [0, 0, 0]
    try:
        async with _build_async_client(handler) as client:
            await seed_initial_state(client, cfg, writer)
    finally:
        runner_mod.SEED_RETRY_BACKOFFS = original
    assert (tmp_path / "clusters.json").exists()
    clusters_doc = json.loads((tmp_path / "clusters.json").read_text())
    assert clusters_doc["resources"] == []  # empty but valid


def test_runner_config_from_env_dynamic_includes_clusters_path():
    cfg = RunnerConfig.from_env({
        "OMNIX_FACADE_MODE": "dynamic",
        "OMNIX_FACADE_CLUSTERS_PATH": "/some/path/clusters.json",
    })
    assert cfg.mode == "dynamic"
    assert cfg.clusters_path == Path("/some/path/clusters.json")


def test_runner_config_from_env_static_skips_clusters_path():
    cfg = RunnerConfig.from_env({"OMNIX_FACADE_MODE": "static"})
    assert cfg.mode == "static"
    assert cfg.clusters_path is None


def test_runner_config_from_env_rejects_unknown_mode():
    with pytest.raises(ValueError, match="OMNIX_FACADE_MODE"):
        RunnerConfig.from_env({"OMNIX_FACADE_MODE": "turbo"})


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
