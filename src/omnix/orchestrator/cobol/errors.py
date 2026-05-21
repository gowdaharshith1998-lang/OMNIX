"""Errors for the COBOL orchestrator backend."""

from __future__ import annotations


class CobolOrchestratorError(RuntimeError):
    """Base error for orchestrator-owned failures."""


class StateCorrupted(CobolOrchestratorError):
    """Run state database cannot be safely resumed."""


class DecisionUnavailable(CobolOrchestratorError):
    """A queued decision cannot be answered in the current execution mode."""


class BudgetExceeded(CobolOrchestratorError):
    """Budget guard blocked further dispatch."""


class InsufficientContext(CobolOrchestratorError):
    """GraphRAG traversal exhausted its context budget."""


class SkillRolledBack(CobolOrchestratorError):
    """A GraphRAG skill was invalidated after regression detection."""
