"""Gate 6 behavioral equivalence harness."""

from omnix.gates.gate6_equivalence.classifier import (
    Classification,
    ClassifiedProbe,
    Gate6Evaluation,
    check,
    classify_results,
    evaluate,
    evaluate_results,
)
from omnix.gates.gate6_equivalence.harness import ProbeResult, run_harness
from omnix.gates.gate6_equivalence.probes import (
    DEFAULT_CONSTRUCT_MARKER,
    FLOAT_MARKER,
    MAX_PROBES_PER_METHOD,
    ProbeInput,
    ProbeSet,
    generate_probe_set,
    generate_probes,
)

__all__ = [
    "Classification",
    "ClassifiedProbe",
    "DEFAULT_CONSTRUCT_MARKER",
    "FLOAT_MARKER",
    "Gate6Evaluation",
    "MAX_PROBES_PER_METHOD",
    "ProbeInput",
    "ProbeResult",
    "ProbeSet",
    "check",
    "classify_results",
    "evaluate",
    "evaluate_results",
    "generate_probe_set",
    "generate_probes",
    "run_harness",
]
