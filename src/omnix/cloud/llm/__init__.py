"""LLM provider fabric — Shape B routing surface.

Routes generation / verification / explanation requests across approved
providers (Anthropic, Bedrock, Claude-Platform-AWS, Vertex, Foundry, OpenAI,
Azure OpenAI, self-hosted Llama/Qwen/DeepSeek) based on tenant tier,
data classification, and job kind.
"""

from __future__ import annotations

from omnix.cloud.llm.provider_fabric import (  # noqa: F401
    Provider,
    ProviderFabric,
    ProviderResult,
    RoutingPolicy,
)
