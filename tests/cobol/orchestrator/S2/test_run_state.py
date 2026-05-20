from __future__ import annotations

from pathlib import Path

import pytest


def test_run_create_add_program_transition_and_resume(tmp_path: Path) -> None:
    from omnix.orchestrator.cobol.discovery import DiscoveredProgram
    from omnix.orchestrator.cobol.run_state import RunState

    state = RunState.create(tmp_path, "python", 5.0)
    program = DiscoveredProgram("HELLO", tmp_path / "HELLO.cob", [], [], None)
    state.add_program(program)
    state.transition("HELLO", "verified", receipt_path=str(tmp_path / "HELLO.json"))
    run_id = state.run_id
    state.close()

    resumed = RunState.resume(run_id, runs_root=tmp_path / ".omnix" / "runs")

    assert resumed.get_pending() == []
    assert resumed.get_terminal()[0].state == "verified"
    resumed.close()


def test_run_state_rejects_invalid_transition_and_corrupted_state(tmp_path: Path) -> None:
    from omnix.orchestrator.cobol.errors import StateCorrupted
    from omnix.orchestrator.cobol.run_state import RunState

    state = RunState.create(tmp_path, "python", 1.0)
    with pytest.raises(ValueError, match="invalid program state"):
        state.transition("MISSING", "verified")
    run_id = state.run_id
    state.close()

    (tmp_path / ".omnix" / "runs" / run_id / "state.db").write_text("not sqlite", encoding="utf-8")
    with pytest.raises(StateCorrupted):
        RunState.resume(run_id, runs_root=tmp_path / ".omnix" / "runs")


def test_progress_events_are_persisted_and_emitted(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from omnix.orchestrator.cobol.progress import JsonProgressEmitter
    from omnix.orchestrator.cobol.run_state import RunState

    emitter = JsonProgressEmitter(run_id="run-x")
    emitter.emit("run_started", {"programs": 1})
    captured = capsys.readouterr()
    assert '"kind": "run_started"' in captured.err

    state = RunState.create(tmp_path, "python", 1.0)
    state.emit_event("custom", {"ok": True})
    assert state.events()[-1]["kind"] == "custom"
    state.close()

