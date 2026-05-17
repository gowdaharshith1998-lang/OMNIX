"""Glue layer from encrypted BYOK storage to ``fabric.dispatcher``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from omnix.fabric.dispatcher import dispatch
from omnix.providers.registry import PROVIDERS
from omnix.receipts.provider_vault import get_key


class ProviderNotRegistered(ValueError):
    """Raised when a caller requests a provider not present in the registry."""


@dataclass(frozen=True)
class CallableProviderClient:
    provider: str
    key: str
    project_id: str | None = None
    custom_base_url: str | None = None
    custom_model: str | None = None

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if self.provider not in PROVIDERS:
            raise ProviderNotRegistered(self.provider)
        options = dict(kwargs.pop("options", {}) or {})
        chosen_model = model or self.custom_model or PROVIDERS[self.provider].default_model
        if chosen_model:
            options["model_override"] = chosen_model
        if self.custom_base_url:
            options["custom_base_url"] = self.custom_base_url
        return dispatch(
            {
                "agent_id": str(kwargs.pop("agent_id", "provider-client")),
                "task_kind": str(kwargs.pop("task_kind", "default")),
                "messages": messages,
                "provider_key": {"provider": self.provider, "key": self.key},
                "options": options,
            }
        )


def get_provider_client(
    provider_name: str,
    project_id: str | None = None,
) -> CallableProviderClient | None:
    if provider_name not in PROVIDERS:
        raise ProviderNotRegistered(provider_name)
    found = get_key(provider_name, project_id)
    if found is None:
        return None
    return CallableProviderClient(
        provider=provider_name,
        key=found.key,
        project_id=project_id,
        custom_base_url=found.metadata.custom_base_url,
        custom_model=found.metadata.custom_model,
    )
