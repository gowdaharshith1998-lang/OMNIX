"""Prompt template — deterministic prompt assembly for the orchestrator.

The template version is pinned (PROMPT_TEMPLATE_VERSION) so receipts can
prove which template produced a given response_text. Same spec + source
must always produce the same prompt text — and therefore the same hash —
which is how Phase 6 verification gates anchor reproducibility.

SCC batching (mutual recursion) goes through `format_scc_prompt`, which
shares the SYSTEM banner but enumerates all specs + sources together so
the model has the whole cycle in one window.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from omnix.orchestrator.attempt import sha256_hex
from omnix.spec import Spec

PROMPT_TEMPLATE_VERSION = "v1-2026-05-17"

SYSTEM_PROMPT = (
    "You are a Java migration expert. Rebuild the following Java 6 method as "
    "idiomatic Java 21, preserving behavior. Output only the Java source — "
    "no commentary, no markdown fences."
)


def format_prompt(spec: Spec, source_code: str) -> tuple[str, str]:
    """Render the single-node prompt and return (text, sha256_hex(text)).

    Layout:
        [SYSTEM]
        <SYSTEM_PROMPT>

        [SPEC]
        <spec.to_json(indent=2)>

        [SOURCE]
        ```java
        <source_code>
        ```
    """
    spec_json = spec.to_json(indent=2)
    text = (
        "[SYSTEM]\n"
        f"{SYSTEM_PROMPT}\n"
        "\n"
        "[SPEC]\n"
        f"{spec_json}\n"
        "\n"
        "[SOURCE]\n"
        "```java\n"
        f"{source_code}\n"
        "```"
    )
    return text, sha256_hex(text)


def format_scc_prompt(
    specs: Sequence[Spec],
    sources: Mapping[str, str],
) -> tuple[str, str]:
    """Render an SCC (mutual-recursion) prompt and return (text, sha256_hex(text)).

    All specs share one SYSTEM banner; SPECS and SOURCES sections enumerate
    every member of the SCC in input order so the model can rebuild the
    whole cycle as one consistent set.

    Args:
        specs: ordered specs for SCC members.
        sources: maps FQN -> source text. Members whose FQN is missing get
            an empty source block (the orchestrator's source loader is the
            authoritative gatekeeper; this function does not enforce).
    """
    specs_section = "\n\n".join(
        f"--- {s.identity.fqn} ---\n{s.to_json(indent=2)}" for s in specs
    )
    sources_section = "\n\n".join(
        f"--- {s.identity.fqn} ---\n```java\n{sources.get(s.identity.fqn, '')}\n```"
        for s in specs
    )
    text = (
        "[SYSTEM]\n"
        f"{SYSTEM_PROMPT}\n"
        "\n"
        "[SCC_NOTE]\n"
        "The following methods form a mutual-recursion cycle. Rebuild them "
        "together so their rebuilt signatures stay consistent.\n"
        "\n"
        "[SPECS]\n"
        f"{specs_section}\n"
        "\n"
        "[SOURCES]\n"
        f"{sources_section}"
    )
    return text, sha256_hex(text)
