from __future__ import annotations

from pathlib import Path


def _request():
    from omnix.orchestrator.cobol.decision_queue import DecisionOption, DecisionRequest

    return DecisionRequest(
        decision_id="d1",
        kind="missing_fixtures",
        context={"program_id": "HELLO"},
        options=(
            DecisionOption("s", "Skip", "Skip and flag", recommended=True),
            DecisionOption("g", "Generate", "Generate synthetic", cost_estimate_usd=0.3),
        ),
        default_key="s",
    )


def test_terminal_queue_timeout_uses_default_and_persists(tmp_path: Path) -> None:
    from omnix.orchestrator.cobol.decision_queue import TerminalDecisionQueue
    from omnix.orchestrator.cobol.run_state import RunState

    state = RunState.create(tmp_path, "python", 1.0)
    queue = TerminalDecisionQueue(state, input_fn=lambda _: "", output_fn=lambda _: None)

    assert queue.ask(_request(), timeout_s=0) == "s"
    assert state.get_decision("d1")["answer"] == "s"
    assert queue.list_pending() == []
    state.close()


def test_decision_already_answered_is_reused(tmp_path: Path) -> None:
    from omnix.orchestrator.cobol.decision_queue import TerminalDecisionQueue
    from omnix.orchestrator.cobol.run_state import RunState

    state = RunState.create(tmp_path, "python", 1.0)
    queue = TerminalDecisionQueue(state, input_fn=lambda _: "g", output_fn=lambda _: None)
    queue.answer("d1", "s")

    assert queue.ask(_request(), timeout_s=60) == "s"
    state.close()

