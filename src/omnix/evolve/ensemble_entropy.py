"""Ensemble Semantic Entropy + Cas cascading test-time verifier."""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from collections.abc import Callable


def ese_mode() -> str:
    mode = os.environ.get("OMNIX_ESE_MODE", "off").strip().lower()
    if mode not in {"off", "auto", "on"}:
        return "off"
    return mode


def ese_threshold() -> float:
    try:
        return float(os.environ.get("OMNIX_ESE_THRESHOLD", "0.6"))
    except ValueError:
        return 0.6


def cluster_outputs_by_normalized_form(outputs: list[str]) -> list[set[int]]:
    groups: dict[str, set[int]] = {}
    for idx, output in enumerate(outputs):
        groups.setdefault(_normalized_output(output), set()).add(idx)
    return list(groups.values())


def semantic_entropy(outputs: list[str]) -> float:
    if not outputs:
        return 0.0
    clusters = cluster_outputs_by_normalized_form(outputs)
    total = len(outputs)
    probs = [len(cluster) / total for cluster in clusters]
    return -sum(prob * math.log(prob) for prob in probs if prob > 0)


def cascading_generate(
    generate_fn: Callable[[str], str],
    cheap_model: str = "gpt-4.1-mini",
    strong_model: str = "gpt-4.1",
    escalate_model: str = "gpt-5",
    n_samples: int = 3,
    entropy_threshold: float | None = None,
) -> tuple[str, dict]:
    threshold = ese_threshold() if entropy_threshold is None else entropy_threshold
    sample_count = max(1, n_samples)
    telemetry: dict = {"stages": []}

    cheap_outputs = [generate_fn(cheap_model) for _ in range(sample_count)]
    entropy = semantic_entropy(cheap_outputs)
    telemetry["stages"].append({"model": cheap_model, "n": sample_count, "entropy": entropy})
    if entropy < threshold:
        return _majority(cheap_outputs), telemetry

    strong_outputs = [generate_fn(strong_model) for _ in range(sample_count)]
    entropy = semantic_entropy(strong_outputs)
    telemetry["stages"].append({"model": strong_model, "n": sample_count, "entropy": entropy})
    if entropy < threshold:
        return _majority(strong_outputs), telemetry

    final = generate_fn(escalate_model)
    telemetry["stages"].append({"model": escalate_model, "n": 1, "entropy": None})
    return final, telemetry


def _majority(outputs: list[str]) -> str:
    if not outputs:
        return ""
    keys = [_normalized_output(output) for output in outputs]
    counts = Counter(keys)
    winning_key = max(counts, key=lambda key: (counts[key], -keys.index(key)))
    return outputs[keys.index(winning_key)]


def _normalized_output(output: str) -> str:
    lines = [re.sub(r"\s+", " ", line.strip()).lower() for line in output.splitlines()]
    return "\n".join(line for line in lines if line)
