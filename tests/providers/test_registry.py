from __future__ import annotations

from omnix.providers.registry import PROVIDERS


def test_registry_contains_universal_byok_set() -> None:
    expected = {
        "anthropic",
        "google_ai",
        "openai",
        "groq",
        "openrouter",
        "xai",
        "deepseek",
        "mistral",
        "cohere",
        "together",
        "nvidia_nim",
        "fireworks",
        "perplexity",
        "lambda_labs",
        "replicate",
        "huggingface",
        "ollama",
        "custom",
    }
    assert expected.issubset(PROVIDERS)


def test_openai_compatible_providers_have_base_url_except_custom() -> None:
    for name, spec in PROVIDERS.items():
        if spec.adapter == "openai_compatible" and name != "custom":
            assert spec.base_url
            assert spec.chat_endpoint.startswith("/")


def test_unverified_provider_strings_are_explicitly_marked() -> None:
    for spec in PROVIDERS.values():
        if not spec.verified:
            assert "TODO: verify with Hg" in spec.verification_note
