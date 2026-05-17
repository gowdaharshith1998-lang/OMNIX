"""omnix.orchestrator — walks the graph, dispatches LLM calls, captures attempts.

Phase 5 ships the dispatch loop (no retry, no gates). Phase 7 adds the retry wrapper.
Verification (Phase 6) lives in omnix.gates and is consumed by the retry wrapper here.
"""

from omnix.orchestrator.attempt import RebuildAttempt

__all__ = ["RebuildAttempt"]
