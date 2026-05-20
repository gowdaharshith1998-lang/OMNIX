from __future__ import annotations

from decimal import Decimal
from pathlib import Path


def test_budget_tracks_warning_and_hard_halt(tmp_path: Path) -> None:
    from omnix.orchestrator.cobol.budget_guard import BudgetCheck, BudgetGuard, BudgetStatus
    from omnix.orchestrator.cobol.decision_queue import TerminalDecisionQueue
    from omnix.orchestrator.cobol.run_state import RunState

    state = RunState.create(tmp_path, "python", 1.0)
    queue = TerminalDecisionQueue(state, input_fn=lambda _: "c", output_fn=lambda _: None)
    guard = BudgetGuard(Decimal("1.00"), state, queue)

    assert guard.record_spend(Decimal("0.80")) == BudgetStatus.WARNING_80
    assert guard.check_before_dispatch(Decimal("0.10")) == BudgetCheck.PROCEED
    assert guard.check_before_dispatch(Decimal("0.21")) == BudgetCheck.BUDGET_EXHAUSTED
    state.close()


def test_budget_warning_decision_can_pause_or_abort(tmp_path: Path) -> None:
    from omnix.orchestrator.cobol.budget_guard import BudgetCheck, BudgetGuard
    from omnix.orchestrator.cobol.decision_queue import TerminalDecisionQueue
    from omnix.orchestrator.cobol.run_state import RunState

    state = RunState.create(tmp_path, "python", 1.0)
    guard = BudgetGuard(Decimal("1.00"), state, TerminalDecisionQueue(state, input_fn=lambda _: "p", output_fn=lambda _: None))
    guard.record_spend(Decimal("0.80"))

    assert guard.check_before_dispatch(Decimal("0.01")) == BudgetCheck.PAUSED
    state.close()

