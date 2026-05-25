"""Scientist port tests."""

from __future__ import annotations

import asyncio

import pytest

from omnix.cloud.verify.scientist import (
    Experiment,
    Mismatch,
    jsonl_publisher,
    list_publisher,
)


def test_agreement_does_not_publish():
    sink: list[Mismatch] = []
    exp = Experiment("legacy-vs-candidate", publisher=list_publisher(sink))
    exp.use(lambda x: x * 2)
    exp.try_(lambda x: x + x)
    assert exp.run(5) == 10
    assert sink == []


def test_mismatch_publishes_but_returns_control():
    sink: list[Mismatch] = []
    exp = Experiment("e", publisher=list_publisher(sink))
    exp.use(lambda x: x * 2)
    exp.try_(lambda x: x * 3)
    assert exp.run(7) == 14
    assert len(sink) == 1
    assert sink[0].candidate.value == 21
    assert sink[0].control.value == 14


def test_candidate_exception_published():
    sink: list[Mismatch] = []
    exp = Experiment("e", publisher=list_publisher(sink))
    exp.use(lambda x: x)
    exp.try_(lambda x: (_ for _ in ()).throw(RuntimeError("boom")))
    assert exp.run(1) == 1
    assert sink and sink[0].candidate.exception


def test_control_exception_propagates():
    sink: list[Mismatch] = []
    exp = Experiment("e", publisher=list_publisher(sink))

    @exp.use
    def control(x):
        raise ValueError("legacy broke")

    @exp.try_
    def candidate(x):
        return x

    with pytest.raises(RuntimeError):
        exp.run(1)


def test_custom_comparator():
    sink: list[Mismatch] = []
    exp = Experiment(
        "e", publisher=list_publisher(sink),
        comparator=lambda a, b: round(a, 3) == round(b, 3),
    )
    exp.use(lambda x: 1.0 / 3.0)
    exp.try_(lambda x: 0.333)
    exp.run(0)
    assert sink == []


def test_enabled_gate_skips_candidate():
    sink: list[Mismatch] = []
    exp = Experiment("e", publisher=list_publisher(sink), enabled=lambda: False)
    exp.use(lambda x: 1)
    exp.try_(lambda x: 2)
    assert exp.run(0) == 1
    assert sink == []


def test_async_run():
    sink: list[Mismatch] = []
    exp = Experiment("e-async", publisher=list_publisher(sink))

    @exp.use
    async def control(x):
        await asyncio.sleep(0)
        return x + 1

    @exp.try_
    async def candidate(x):
        await asyncio.sleep(0)
        return x + 2

    assert asyncio.run(exp.run_async(10)) == 11
    assert len(sink) == 1


def test_jsonl_publisher_appends(tmp_path):
    path = tmp_path / "mismatches.jsonl"
    exp = Experiment("e", publisher=jsonl_publisher(path))
    exp.use(lambda x: x)
    exp.try_(lambda x: x + 1)
    exp.run(0)
    exp.run(1)
    content = path.read_text().strip().splitlines()
    assert len(content) == 2
