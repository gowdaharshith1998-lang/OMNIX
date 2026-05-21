"""Parse and evaluate sufficient-context signals."""

from __future__ import annotations

from dataclasses import dataclass

from omnix.enrich.common import parse_jsonish


@dataclass(frozen=True)
class ConfidenceSignal:
    sufficient: bool
    confidence: float


def parse_sufficient_signal(model_output: str) -> ConfidenceSignal | None:
    parsed = parse_jsonish(model_output)
    if not isinstance(parsed, dict) or "sufficient" not in parsed:
        return None
    try:
        return ConfidenceSignal(bool(parsed.get("sufficient")), float(parsed.get("confidence", 0.0)))
    except (TypeError, ValueError):
        return None


def should_grant_extra_hop(signal: ConfidenceSignal, threshold: float = 0.75) -> bool:
    return signal.sufficient and signal.confidence < threshold
