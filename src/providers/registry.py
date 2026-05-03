"""Static Provider Fabric registry for Universal BYOK.

URLs and model names are intentionally data, not routing code. Entries marked
``verification_note`` with TODO require Hg live-doc/manual confirmation before
being treated as canonical defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

AdapterName = Literal["anthropic", "openai_compatible", "google", "ollama"]


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    display_name: str
    adapter: AdapterName
    prefix_patterns: tuple[str, ...]
    base_url: str | None
    default_model: str | None
    probe_endpoint: str
    probe_auth: tuple[str, str] | None = None
    probe_extra_headers: dict[str, str] = field(default_factory=dict)
    chat_endpoint: str = "/chat/completions"
    verified: bool = True
    verification_note: str = ""


PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        name="anthropic",
        display_name="Anthropic",
        adapter="anthropic",
        prefix_patterns=("sk-ant-",),
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-4-6",
        probe_endpoint="/v1/models",
        probe_auth=("x-api-key", "{key}"),
        probe_extra_headers={"anthropic-version": "2023-06-01"},
    ),
    "google_ai": ProviderSpec(
        name="google_ai",
        display_name="Google AI",
        adapter="google",
        prefix_patterns=("AIza",),
        base_url="https://generativelanguage.googleapis.com",
        default_model="gemini-2.5-flash",
        probe_endpoint="/v1beta/models?key={key}",
    ),
    "google": ProviderSpec(
        name="google",
        display_name="Google AI",
        adapter="google",
        prefix_patterns=("AIza",),
        base_url="https://generativelanguage.googleapis.com",
        default_model="gemini-2.5-flash",
        probe_endpoint="/v1beta/models?key={key}",
        verification_note="Compatibility alias for existing Fabric configs.",
    ),
    "ollama": ProviderSpec(
        name="ollama",
        display_name="Ollama",
        adapter="ollama",
        prefix_patterns=(),
        base_url="http://localhost:11434",
        default_model="llama3.2:latest",
        probe_endpoint="/api/tags",
    ),
    "openai": ProviderSpec(
        name="openai",
        display_name="OpenAI",
        adapter="openai_compatible",
        prefix_patterns=("sk-proj-", "sk-"),
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o",
        probe_endpoint="/models",
        probe_auth=("Authorization", "Bearer {key}"),
    ),
    "groq": ProviderSpec(
        name="groq",
        display_name="Groq",
        adapter="openai_compatible",
        prefix_patterns=("gsk_",),
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        probe_endpoint="/models",
        probe_auth=("Authorization", "Bearer {key}"),
    ),
    "openrouter": ProviderSpec(
        name="openrouter",
        display_name="OpenRouter",
        adapter="openai_compatible",
        prefix_patterns=("sk-or-v1-",),
        base_url="https://openrouter.ai/api/v1",
        default_model="anthropic/claude-sonnet-4.6",
        probe_endpoint="/models",
        probe_auth=("Authorization", "Bearer {key}"),
    ),
    "xai": ProviderSpec(
        name="xai",
        display_name="xAI",
        adapter="openai_compatible",
        prefix_patterns=("xai-",),
        base_url="https://api.x.ai/v1",
        default_model="grok-4.3",
        probe_endpoint="/models",
        probe_auth=("Authorization", "Bearer {key}"),
    ),
    "deepseek": ProviderSpec(
        name="deepseek",
        display_name="DeepSeek",
        adapter="openai_compatible",
        prefix_patterns=("sk-",),
        base_url="https://api.deepseek.com",
        default_model="deepseek-v4-pro",
        probe_endpoint="/models",
        probe_auth=("Authorization", "Bearer {key}"),
    ),
    "mistral": ProviderSpec(
        name="mistral",
        display_name="Mistral",
        adapter="openai_compatible",
        prefix_patterns=(),
        base_url="https://api.mistral.ai/v1",
        default_model="mistral-large-latest",
        probe_endpoint="/models",
        probe_auth=("Authorization", "Bearer {key}"),
    ),
    "cohere": ProviderSpec(
        name="cohere",
        display_name="Cohere",
        adapter="openai_compatible",
        prefix_patterns=(),
        base_url="https://api.cohere.com/v1",
        default_model="command-r-plus",
        probe_endpoint="/models",
        probe_auth=("Authorization", "Bearer {key}"),
        verified=False,
        verification_note="# TODO: verify with Hg: Cohere /v1/models confirmed, OpenAI-compatible chat model default needs live account confirmation.",
    ),
    "together": ProviderSpec(
        name="together",
        display_name="Together AI",
        adapter="openai_compatible",
        prefix_patterns=(),
        base_url="https://api.together.ai/v1",
        default_model="openai/gpt-oss-20b",
        probe_endpoint="/models",
        probe_auth=("Authorization", "Bearer {key}"),
    ),
    "nvidia_nim": ProviderSpec(
        name="nvidia_nim",
        display_name="NVIDIA NIM",
        adapter="openai_compatible",
        prefix_patterns=("nvapi-",),
        base_url="https://integrate.api.nvidia.com/v1",
        default_model="meta/llama-3.3-70b-instruct",
        probe_endpoint="/models",
        probe_auth=("Authorization", "Bearer {key}"),
        verified=False,
        verification_note="# TODO: verify with Hg: NVIDIA docs confirm base/chat; /models availability should be live-tested.",
    ),
    "fireworks": ProviderSpec(
        name="fireworks",
        display_name="Fireworks AI",
        adapter="openai_compatible",
        prefix_patterns=("fw_",),
        base_url="https://api.fireworks.ai/inference/v1",
        default_model="accounts/fireworks/models/deepseek-v3p1",
        probe_endpoint="/models",
        probe_auth=("Authorization", "Bearer {key}"),
        verified=False,
        verification_note="# TODO: verify with Hg: Fireworks OpenAI chat base confirmed; account-scoped model listing differs.",
    ),
    "perplexity": ProviderSpec(
        name="perplexity",
        display_name="Perplexity",
        adapter="openai_compatible",
        prefix_patterns=("pplx-",),
        base_url="https://api.perplexity.ai",
        default_model="sonar-pro",
        probe_endpoint="/chat/completions",
        probe_auth=("Authorization", "Bearer {key}"),
        verified=False,
        verification_note="# TODO: verify with Hg: Perplexity has no safe GET /models; probe should use manual override/live key test.",
    ),
    "lambda_labs": ProviderSpec(
        name="lambda_labs",
        display_name="Lambda Labs",
        adapter="openai_compatible",
        prefix_patterns=(),
        base_url="https://api.lambda.ai/v1",
        default_model="hermes3-405b-fp8-128k",
        probe_endpoint="/models",
        probe_auth=("Authorization", "Bearer {key}"),
        verified=False,
        verification_note="# TODO: verify with Hg: Lambda Inference API appears winding down; endpoint/model are not official-doc verified.",
    ),
    "replicate": ProviderSpec(
        name="replicate",
        display_name="Replicate",
        adapter="openai_compatible",
        prefix_patterns=("r8_",),
        base_url="https://openai-proxy.replicate.com/v1",
        default_model="meta/meta-llama-3-70b-instruct",
        probe_endpoint="/models",
        probe_auth=("Authorization", "Bearer {key}"),
        verified=False,
        verification_note="# TODO: verify with Hg: Replicate OpenAI proxy was only secondary-source verified.",
    ),
    "huggingface": ProviderSpec(
        name="huggingface",
        display_name="Hugging Face",
        adapter="openai_compatible",
        prefix_patterns=("hf_",),
        base_url="https://router.huggingface.co/v1",
        default_model="meta-llama/Meta-Llama-3.1-8B-Instruct:fastest",
        probe_endpoint="/models",
        probe_auth=("Authorization", "Bearer {key}"),
    ),
    "custom": ProviderSpec(
        name="custom",
        display_name="Custom (OpenAI-compatible)",
        adapter="openai_compatible",
        prefix_patterns=(),
        base_url=None,
        default_model=None,
        probe_endpoint="/models",
        probe_auth=("Authorization", "Bearer {key}"),
    ),
}

PREFIX_PRIORITY = (
    "anthropic",
    "google_ai",
    "groq",
    "openrouter",
    "xai",
    "nvidia_nim",
    "fireworks",
    "perplexity",
    "replicate",
    "huggingface",
    "openai",
    "deepseek",
)

AMBIGUOUS_PROBE_PRIORITY = ("openai", "deepseek")
PREFIXLESS_PROBE_PRIORITY = ("mistral", "cohere", "together", "lambda_labs")


def valid_provider_names() -> frozenset[str]:
    return frozenset(PROVIDERS)


def display_name(name: str) -> str:
    spec = PROVIDERS.get(name)
    return spec.display_name if spec else name


def with_custom(spec: ProviderSpec, *, base_url: str, model: str | None) -> ProviderSpec:
    return replace(spec, base_url=base_url, default_model=model or spec.default_model)
