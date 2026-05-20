"""Budget guard for bounded COBOL orchestration runs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from omnix.orchestrator.cobol.decision_queue import DecisionOption, DecisionQueue, DecisionRequest
from omnix.orchestrator.cobol.run_state import RunState


class BudgetStatus(Enum):
    OK = "ok"
    WARNING_80 = "warning_80"
    HALT_100 = "halt_100"


class BudgetCheck(Enum):
    PROCEED = "proceed"
    PAUSED = "paused"
    ABORTED = "aborted"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass
class BudgetGuard:
    budget_usd: Decimal
    run_state: RunState
    decision_queue: DecisionQueue
    warning_fired: bool = False

    def record_spend(self, amount_usd: Decimal) -> BudgetStatus:
        self.run_state.add_spend(amount_usd)
        total = self.total_spent()
        if total >= self.budget_usd:
            return BudgetStatus.HALT_100
        if not self.warning_fired and self.budget_usd > 0 and total >= self.budget_usd * Decimal("0.80"):
            self.warning_fired = True
            self.run_state.emit_event("budget_warning", {"spent_usd": str(total), "budget_usd": str(self.budget_usd)})
            return BudgetStatus.WARNING_80
        return BudgetStatus.OK

    def check_before_dispatch(self, estimated_usd: Decimal) -> BudgetCheck:
        total = self.total_spent()
        if total + estimated_usd > self.budget_usd:
            return BudgetCheck.BUDGET_EXHAUSTED
        if self.warning_fired:
            decision = self.decision_queue.ask(
                DecisionRequest(
                    decision_id=f"budget-{self.run_state.run_id}",
                    kind="budget_warning",
                    context={"spent_usd": str(total), "budget_usd": str(self.budget_usd)},
                    options=(
                        DecisionOption("c", "Continue", "Continue within remaining budget", recommended=True),
                        DecisionOption("p", "Pause", "Pause this run for later resume"),
                        DecisionOption("a", "Abort", "Abort the run now"),
                    ),
                    default_key="c",
                ),
                timeout_s=0,
            )
            if decision == "p":
                return BudgetCheck.PAUSED
            if decision == "a":
                return BudgetCheck.ABORTED
        return BudgetCheck.PROCEED

    def total_spent(self) -> Decimal:
        return self.run_state.total_spend()

