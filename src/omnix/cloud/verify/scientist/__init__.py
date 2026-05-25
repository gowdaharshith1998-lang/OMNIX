"""Python port of GitHub Scientist — in-process dual-run.

Usage:
    exp = Experiment("legacy-vs-candidate", publisher=jsonl_publisher("mismatches.jsonl"))
    @exp.use
    def control(x): return legacy(x)
    @exp.try_
    def candidate(x): return rewritten(x)
    result = exp.run(42)   # returns control's value; logs mismatch if candidate disagrees

The class is async-safe: ``run_async`` awaits both branches concurrently.
"""

from __future__ import annotations

from omnix.cloud.verify.scientist.core import (  # noqa: F401
    Experiment,
    Mismatch,
    ResultPublisher,
    jsonl_publisher,
    list_publisher,
)
