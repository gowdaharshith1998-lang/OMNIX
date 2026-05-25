"""Diffy noise-filtered proxy tests."""

from __future__ import annotations

import pytest

from omnix.cloud.verify.diffy import DiffyProxy, NoiseFilter, semantic_diff


def test_semantic_diff_flat():
    assert semantic_diff({"a": 1, "b": 2}, {"a": 1, "b": 2}) == set()
    assert semantic_diff({"a": 1}, {"a": 2}) == {"a"}


def test_semantic_diff_nested():
    a = {"x": {"y": 1, "z": [1, 2, 3]}}
    b = {"x": {"y": 1, "z": [1, 2, 4]}}
    assert semantic_diff(a, b) == {"x.z[2]"}


def test_noise_filter_subtracts_known_noise():
    primary = {"id": 1, "ts": 100, "result": "ok"}
    secondary = {"id": 2, "ts": 200, "result": "ok"}
    nf = NoiseFilter()
    nf.observe(primary, secondary)
    assert nf.paths == {"id", "ts"}
    diff = semantic_diff(primary, {"id": 99, "ts": 300, "result": "fail"})
    assert "result" in nf.filter(diff)
    assert "id" not in nf.filter(diff)


@pytest.mark.asyncio
async def test_diffy_proxy_with_fake_sender():
    """Three in-process endpoints; candidate diverges only on result.value."""

    async def fake_sender(url: str, payload: dict):
        if "primary" in url:
            return {"id": "p", "ts": 1, "value": 42}, 200
        if "secondary" in url:
            return {"id": "s", "ts": 2, "value": 42}, 200
        if "candidate" in url:
            return {"id": "c", "ts": 3, "value": 999}, 200
        raise RuntimeError(f"unknown: {url}")

    proxy = DiffyProxy(
        primary="http://primary",
        secondary="http://secondary",
        candidate="http://candidate",
        sender=fake_sender,
    )
    r = await proxy.forward("req-1", {"q": 1})
    # id + ts are noise.
    assert "value" in r.candidate_diff_after_noise
    assert "id" not in r.candidate_diff_after_noise
    assert "ts" not in r.candidate_diff_after_noise
    assert proxy.report.mismatched == 1
    assert proxy.report.matched == 0


@pytest.mark.asyncio
async def test_diffy_proxy_clean_match():
    async def fake_sender(url: str, payload: dict):
        if "primary" in url or "secondary" in url:
            return {"id": "x", "value": 42}, 200
        return {"id": "x", "value": 42}, 200

    proxy = DiffyProxy(
        primary="http://primary",
        secondary="http://secondary",
        candidate="http://candidate",
        sender=fake_sender,
    )
    r = await proxy.forward("req-1", {})
    assert r.candidate_diff_after_noise == set()
    assert proxy.report.matched == 1
