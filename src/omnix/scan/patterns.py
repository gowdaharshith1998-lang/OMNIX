# Compliance: P11, P21

"""
Known provider value patterns and masking.

Compliance: P11, P14, P21
"""

from __future__ import annotations

import re

# Order: anthropic before openai (sk-ant- would match sk- openai loosely otherwise).
RE_ANTHROPIC = re.compile(
    r"^sk-ant-(api03|sid01|admin01)-[A-Za-z0-9_-]{20,}$"
)
RE_OPENAI = re.compile(r"^sk-(?!ant-)(proj-)?[A-Za-z0-9_-]{20,}$")
RE_GOOGLE = re.compile(r"^AIza[A-Za-z0-9_-]{30,}$")


def classify_credential(value: str) -> str | None:
    """
    Return provider id for a candidate secret string, or None.
    Tries Anthropic, Google/Gemini, then OpenAI.
    """
    s = value.strip()
    if not s:
        return None
    if RE_ANTHROPIC.match(s):
        return "anthropic"
    if RE_GOOGLE.match(s):
        return "google"
    if RE_OPENAI.match(s):
        return "openai"
    return None


def masked_preview(provider: str, key_value: str) -> str:
    """Build a non-revealing preview (last 4 characters visible; Ollama special-case)."""
    s = str(key_value)
    if provider == "ollama" and not s.strip():
        return "local-no-auth-needed"
    if len(s) < 4:
        return "****"
    if len(s) <= 8:
        return f"{s[:1]}****{s[-4:]}"
    return f"{s[:12]}****...{s[-4:]}"
