from __future__ import annotations

import math


def test_low_entropy_returns_majority_no_escalation() -> None:
    from omnix.evolve.ensemble_entropy import cascading_generate

    calls = []

    def generate(model: str) -> str:
        calls.append(model)
        return "OK\n"

    chosen, telemetry = cascading_generate(generate, n_samples=3, entropy_threshold=0.6)

    assert chosen == "OK\n"
    assert calls == ["gpt-4.1-mini", "gpt-4.1-mini", "gpt-4.1-mini"]
    assert len(telemetry["stages"]) == 1


def test_high_entropy_escalates_to_strong() -> None:
    from omnix.evolve.ensemble_entropy import cascading_generate

    cheap = iter(["A", "B", "C"])
    strong = iter(["Z", "Z", "Y"])

    def generate(model: str) -> str:
        return next(cheap if model == "gpt-4.1-mini" else strong)

    chosen, telemetry = cascading_generate(generate, n_samples=3, entropy_threshold=0.7)

    assert chosen == "Z"
    assert [stage["model"] for stage in telemetry["stages"]] == ["gpt-4.1-mini", "gpt-4.1"]


def test_persistent_high_entropy_escalates_to_top() -> None:
    from omnix.evolve.ensemble_entropy import cascading_generate

    calls = []

    def generate(model: str) -> str:
        calls.append(model)
        return f"{model}:{len(calls)}"

    chosen, telemetry = cascading_generate(generate, n_samples=3, entropy_threshold=0.01)

    assert chosen.startswith("gpt-5:")
    assert [stage["model"] for stage in telemetry["stages"]] == ["gpt-4.1-mini", "gpt-4.1", "gpt-5"]


def test_empty_outputs_returns_zero_entropy() -> None:
    from omnix.evolve.ensemble_entropy import semantic_entropy

    assert semantic_entropy([]) == 0.0


def test_identical_outputs_zero_entropy() -> None:
    from omnix.evolve.ensemble_entropy import semantic_entropy

    assert semantic_entropy(["OK\n", "OK\n", "OK\n"]) == 0.0


def test_all_unique_outputs_max_entropy() -> None:
    from omnix.evolve.ensemble_entropy import semantic_entropy

    assert math.isclose(semantic_entropy(["A", "B", "C"]), math.log(3), rel_tol=1e-9)


def test_normalization_collapses_whitespace_only_diffs() -> None:
    from omnix.evolve.ensemble_entropy import cluster_outputs_by_normalized_form, semantic_entropy

    outputs = ["TOTAL    10\n", " total 10 ", "TOTAL 10\n\n"]

    assert len(cluster_outputs_by_normalized_form(outputs)) == 1
    assert semantic_entropy(outputs) == 0.0


def test_cas_telemetry_records_stages() -> None:
    from omnix.evolve.ensemble_entropy import cascading_generate

    calls = []

    def generate(model: str) -> str:
        calls.append(model)
        return f"{model}:{len(calls)}"

    chosen, telemetry = cascading_generate(generate, n_samples=2, entropy_threshold=0.01)

    assert chosen.startswith("gpt-5:")
    assert telemetry["stages"][-1] == {"model": "gpt-5", "n": 1, "entropy": None}
