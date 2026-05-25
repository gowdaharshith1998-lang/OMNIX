"""In-process event-bus tests."""

from __future__ import annotations

import asyncio

import pytest

from omnix.cloud import events


@pytest.fixture(autouse=True)
def _reset_bus():
    events.reset_bus()
    yield
    events.reset_bus()


def test_seq_monotonic():
    events.publish("job-1", "ingest", "hi")
    events.publish("job-1", "ingest", "hi again")
    hist = events.history("job-1")
    assert [e.seq for e in hist] == [1, 2]


def test_history_separated_by_job():
    events.publish("a", "x", "for a")
    events.publish("b", "x", "for b")
    assert len(events.history("a")) == 1
    assert len(events.history("b")) == 1


@pytest.mark.asyncio
async def test_subscribe_receives_live_events():
    received: list[events.JobEvent] = []

    async def consumer():
        async for ev in events.subscribe("job-x", replay=False):
            received.append(ev)
            if len(received) >= 2:
                break

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.01)
    events.publish("job-x", "g1", "one")
    events.publish("job-x", "g1", "two")
    await asyncio.wait_for(task, timeout=1.0)
    assert [e.message for e in received] == ["one", "two"]


@pytest.mark.asyncio
async def test_subscribe_replays_history_first():
    events.publish("job-y", "g", "old1")
    events.publish("job-y", "g", "old2")

    received: list[str] = []

    async def consumer():
        async for ev in events.subscribe("job-y", replay=True):
            received.append(ev.message)
            if len(received) >= 2:
                break

    await asyncio.wait_for(consumer(), timeout=1.0)
    assert received == ["old1", "old2"]
