"""Provider Fabric — LLM router.

Each Provider implements:
    complete(prompt, *, system=None, **kwargs) -> ProviderResult

RoutingPolicy:
    classes_to_providers: dict[str, list[str]]   ordered preference list per
                                                  data classification
                                                  (e.g. "FOUO" -> ["bedrock"])
    failover_enabled:     bool                    on primary error, try next

Tests use the ``StubProvider`` so we can verify routing/failover without
network calls. Production wires ``AnthropicProvider`` / ``BedrockProvider`` /
``VertexProvider`` / ``SelfHostedProvider`` via the configmap.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderResult:
    provider: str
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    cache_hit: bool = False
    metadata: dict = field(default_factory=dict)


class ProviderError(RuntimeError):
    pass


class Provider(ABC):
    name: str = "abstract"
    model: str = "unknown"

    @abstractmethod
    def complete(self, prompt: str, *, system: str | None = None,
                 max_tokens: int = 4096, temperature: float = 0.0,
                 **kwargs: Any) -> ProviderResult:
        ...


class StubProvider(Provider):
    """In-process stub. Tests pre-program the response and the optional
    failure flag."""

    def __init__(self, name: str, model: str = "stub", *,
                 response: str = "OK", fail: bool = False,
                 input_tokens: int = 0, output_tokens: int = 0,
                 cost_per_call: float = 0.0) -> None:
        self.name = name
        self.model = model
        self._response = response
        self._fail = fail
        self._cost = cost_per_call
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self.calls: list[dict[str, Any]] = []

    def complete(self, prompt: str, *, system: str | None = None,
                 max_tokens: int = 4096, temperature: float = 0.0,
                 **kwargs: Any) -> ProviderResult:
        self.calls.append({"prompt": prompt, "system": system, "kwargs": kwargs})
        if self._fail:
            raise ProviderError(f"stub provider {self.name} configured to fail")
        return ProviderResult(
            provider=self.name,
            text=self._response,
            model=self.model,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            cost_usd=self._cost,
        )


@dataclass
class RoutingPolicy:
    """Pure routing rules.

    classes_to_providers maps a data-classification string (or tier name)
    to an ordered preference list of provider names.
    """
    classes_to_providers: Mapping[str, list[str]] = field(default_factory=dict)
    default_classification: str = "smb_default"
    failover_enabled: bool = True

    def resolve(self, classification: str) -> list[str]:
        return list(self.classes_to_providers.get(
            classification,
            self.classes_to_providers.get(self.default_classification, []),
        ))


class ProviderFabric:
    def __init__(self, providers: Mapping[str, Provider], policy: RoutingPolicy) -> None:
        self._providers: dict[str, Provider] = dict(providers)
        self._policy = policy
        self._costs: dict[str, float] = {}
        self._calls: dict[str, int] = {}

    @property
    def costs(self) -> dict[str, float]:
        return dict(self._costs)

    @property
    def call_counts(self) -> dict[str, int]:
        return dict(self._calls)

    def route(self, *, classification: str | None = None) -> list[Provider]:
        names = self._policy.resolve(classification or self._policy.default_classification)
        out: list[Provider] = []
        for n in names:
            p = self._providers.get(n)
            if p is not None:
                out.append(p)
        if not out:
            raise ProviderError(
                f"no providers resolved for classification={classification!r}"
            )
        return out

    def complete(self, prompt: str, *, classification: str | None = None,
                 **kwargs: Any) -> ProviderResult:
        last_exc: Exception | None = None
        for provider in self.route(classification=classification):
            try:
                result = provider.complete(prompt, **kwargs)
                self._costs[provider.name] = self._costs.get(provider.name, 0.0) + result.cost_usd
                self._calls[provider.name] = self._calls.get(provider.name, 0) + 1
                return result
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if not self._policy.failover_enabled:
                    raise
        raise ProviderError(
            f"all providers exhausted (classification={classification!r}): {last_exc}"
        )


def from_configmap(
    cfg: Mapping[str, Any], provider_factory=None,
) -> ProviderFabric:
    """Build a fabric from a parsed configmap-provider-fabric.yaml shape.

    See deploy/helm/omnix/templates/configmap-provider-fabric.yaml for the
    expected schema. ``provider_factory(name, spec)`` returns a Provider.
    """
    if provider_factory is None:
        def provider_factory(name: str, spec: dict) -> Provider:
            return StubProvider(name=name, model=spec.get("model", "unknown"))

    providers: dict[str, Provider] = {}
    for name, spec in cfg.get("providers", {}).items():
        providers[name] = provider_factory(name, spec)

    policy = RoutingPolicy(
        classes_to_providers={
            classification: list(provider_names)
            for classification, provider_names in cfg.get("routing", {}).items()
        }
    )
    return ProviderFabric(providers, policy)
