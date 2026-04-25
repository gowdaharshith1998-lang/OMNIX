"""Shared result types for Layer 6 (universal PBT) runners."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Layer6Result:
    """Result of a single (file, function) run."""

    findings: list[dict[str, Any]] = field(default_factory=list)
    language: str = "unknown"
    runner_used: str = "subprocess_llm"
    extra_metadata: dict[str, Any] = field(default_factory=dict)
    ex_total: int = 0
