from __future__ import annotations

import asyncio
from typing import Any

from omnix.fabric.providers import common
from omnix.providers.detect import identify_provider


def test_anthropic_prefix_is_instant(monkeypatch: Any) -> None:
    monkeypatch.setattr(common, "request_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    r = asyncio.run(identify_provider("sk-ant-api03-fake"))
    assert r.provider == "anthropic"
    assert r.method == "prefix"


def test_groq_prefix_is_instant() -> None:
    r = asyncio.run(identify_provider("gsk_fake"))
    assert r.provider == "groq"


def test_sk_proj_prefers_openai_without_probe() -> None:
    r = asyncio.run(identify_provider("sk-proj-fake"))
    assert r.provider == "openai"
    assert r.method == "prefix"


def test_ambiguous_sk_probes_openai_then_deepseek(monkeypatch: Any) -> None:
    calls: list[str] = []

    def fake_request(url: str, **kwargs: Any) -> tuple[int, dict[str, object]]:
        calls.append(url)
        return (401, {}) if "openai.com" in url else (200, {})

    monkeypatch.setattr("omnix.providers.detect.request_json", fake_request)
    r = asyncio.run(identify_provider("sk-ambiguous"))
    assert r.provider == "deepseek"
    assert r.method == "probe"
    assert "openai.com" in calls[0]


def test_custom_base_url_short_circuits() -> None:
    r = asyncio.run(identify_provider("anything", custom_base_url="http://localhost:8000/v1"))
    assert r.provider == "custom"
    assert r.method == "user_specified"


def test_unknown_when_all_prefixless_probes_fail(monkeypatch: Any) -> None:
    monkeypatch.setattr("omnix.providers.detect.request_json", lambda *a, **k: (401, {}))
    r = asyncio.run(identify_provider("prefixless-key"))
    assert r.provider == "unknown"
    assert r.confidence == 0.0
