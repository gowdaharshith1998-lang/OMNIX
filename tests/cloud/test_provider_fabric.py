"""Provider Fabric routing + failover tests."""

from __future__ import annotations

import json

import pytest

from omnix.cloud.llm.provider_fabric import (
    ProviderError,
    ProviderFabric,
    RoutingPolicy,
    StubProvider,
    from_configmap,
)


def _two_provider_fabric(*, primary_fail: bool = False,
                         secondary_fail: bool = False):
    primary = StubProvider("anthropic", model="claude-opus-4-7",
                           response="primary", fail=primary_fail,
                           cost_per_call=0.05)
    secondary = StubProvider("bedrock", model="anthropic.claude-opus-4-7-v1:0",
                             response="secondary", fail=secondary_fail,
                             cost_per_call=0.04)
    policy = RoutingPolicy(
        classes_to_providers={
            "smb_default": ["anthropic", "bedrock"],
            "fedramp_high": ["bedrock"],
        }
    )
    return ProviderFabric({"anthropic": primary, "bedrock": secondary}, policy), primary, secondary


def test_routes_to_primary_on_success():
    fabric, primary, secondary = _two_provider_fabric()
    result = fabric.complete("hello")
    assert result.provider == "anthropic"
    assert result.text == "primary"
    assert primary.calls and not secondary.calls


def test_failover_on_primary_error():
    fabric, primary, secondary = _two_provider_fabric(primary_fail=True)
    result = fabric.complete("hello")
    assert result.provider == "bedrock"
    assert result.text == "secondary"
    assert primary.calls and secondary.calls


def test_raises_when_all_fail():
    fabric, _, _ = _two_provider_fabric(primary_fail=True, secondary_fail=True)
    with pytest.raises(ProviderError):
        fabric.complete("hello")


def test_classification_routes_correctly():
    fabric, primary, secondary = _two_provider_fabric()
    result = fabric.complete("x", classification="fedramp_high")
    assert result.provider == "bedrock"
    assert not primary.calls


def test_cost_and_call_tracking():
    fabric, *_ = _two_provider_fabric()
    fabric.complete("one")
    fabric.complete("two")
    assert fabric.call_counts["anthropic"] == 2
    assert abs(fabric.costs["anthropic"] - 0.10) < 1e-9


def test_failover_disabled_raises_first_error():
    primary = StubProvider("p", fail=True)
    secondary = StubProvider("s")
    fabric = ProviderFabric(
        {"p": primary, "s": secondary},
        RoutingPolicy(
            classes_to_providers={"smb_default": ["p", "s"]},
            failover_enabled=False,
        ),
    )
    with pytest.raises(ProviderError):
        fabric.complete("x")


def test_from_configmap_builds_fabric():
    cfg = json.loads("""{
        "providers": {
            "anthropic": {"kind": "anthropic", "model": "claude-opus-4-7"},
            "selfhosted": {"kind": "self-hosted", "endpoint": "http://vllm:8000", "model": "llama-3.3-70b"}
        },
        "routing": {
            "smb_default": ["anthropic"],
            "fully_airgapped": ["selfhosted"]
        }
    }""")
    fabric = from_configmap(cfg)
    assert fabric.route(classification="smb_default")[0].name == "anthropic"
    assert fabric.route(classification="fully_airgapped")[0].name == "selfhosted"


def test_unknown_classification_falls_back_to_default():
    fabric, *_ = _two_provider_fabric()
    result = fabric.complete("x", classification="unknown_class")
    assert result.provider == "anthropic"


def test_route_returns_ordered_providers():
    fabric, primary, secondary = _two_provider_fabric()
    chain = fabric.route(classification="smb_default")
    assert [p.name for p in chain] == ["anthropic", "bedrock"]
