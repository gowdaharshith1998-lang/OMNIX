"""OMNIX LLM Router — auto-detects Ollama, Groq, Anthropic, OpenAI."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class LLMRouter:
    """Routes LLM calls to the best available provider."""

    def __init__(self) -> None:
        self.provider: str | None = None
        self.api_key: str | None = None
        self.base_url: str | None = None
        self.model: str | None = None
        self._detect_provider()

    def _detect_provider(self) -> None:
        """Auto-detect available LLM provider. Priority: Ollama → Groq → Anthropic → OpenAI."""

        explicit = os.environ.get("OMNIX_AI_PROVIDER", "").lower()
        key = os.environ.get("OMNIX_AI_KEY", "")

        if explicit:
            self._configure_explicit(explicit, key)
            return

        if key:
            if key.startswith("gsk_"):
                self._configure_groq(key)
                return
            if key.startswith("sk-ant-"):
                self._configure_anthropic(key)
                return
            if key.startswith("sk-"):
                self._configure_openai(key)
                return

        if self._check_ollama():
            return

        self.provider = None

    def _check_ollama(self) -> bool:
        """Check if Ollama is running on localhost."""
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode())
                models = [m["name"] for m in data.get("models", [])]
                preferred = [
                    "qwen2.5-coder",
                    "codellama",
                    "deepseek-coder",
                    "llama3",
                    "mistral",
                ]
                self.model = None
                for p in preferred:
                    for m in models:
                        if p in m:
                            self.model = m
                            break
                    if self.model:
                        break
                if not self.model and models:
                    self.model = models[0]
                if self.model:
                    self.provider = "ollama"
                    self.base_url = "http://localhost:11434"
                    return True
        except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, ValueError):
            pass
        return False

    def _configure_groq(self, key: str) -> None:
        self.provider = "groq"
        self.api_key = key
        self.base_url = "https://api.groq.com/openai/v1"
        self.model = "llama-3.3-70b-versatile"

    def _configure_anthropic(self, key: str) -> None:
        self.provider = "anthropic"
        self.api_key = key
        self.base_url = "https://api.anthropic.com"
        self.model = "claude-sonnet-4-20250514"

    def _configure_openai(self, key: str) -> None:
        self.provider = "openai"
        self.api_key = key
        self.base_url = "https://api.openai.com/v1"
        self.model = "gpt-4o"

    def _configure_explicit(self, provider: str, key: str) -> None:
        if provider == "ollama":
            self._check_ollama()
        elif provider == "groq":
            self._configure_groq(key)
        elif provider == "anthropic":
            self._configure_anthropic(key)
        elif provider == "openai":
            self._configure_openai(key)

    @property
    def available(self) -> bool:
        return self.provider is not None

    @property
    def info(self) -> str:
        if not self.available:
            return "No AI provider detected. Set OMNIX_AI_KEY or install Ollama."
        return f"{self.provider} ({self.model})"

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> dict[str, str]:
        """Send a chat completion request to the detected provider."""
        if not self.available:
            return {"error": "No AI provider available"}

        try:
            if self.provider == "ollama":
                return self._chat_ollama(messages, temperature, max_tokens)
            if self.provider == "anthropic":
                return self._chat_anthropic(messages, temperature, max_tokens)
            return self._chat_openai_compatible(messages, temperature, max_tokens)
        except Exception as e:
            return {"error": str(e)}

    def _chat_ollama(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, str]:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            return {
                "content": data.get("message", {}).get("content", ""),
                "provider": "ollama",
            }

    def _chat_anthropic(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, str]:
        system = ""
        chat_messages: list[dict[str, str]] = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                chat_messages.append(m)

        body: dict[str, object] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat_messages,
        }
        if system:
            body["system"] = system

        payload = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key or "",
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            content = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block["text"]
            return {"content": content, "provider": "anthropic"}

    def _chat_openai_compatible(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, str]:
        """Works for OpenAI and Groq (same API format)."""
        payload = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            content = data["choices"][0]["message"]["content"]
            return {"content": content, "provider": self.provider or "openai"}
