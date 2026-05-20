from __future__ import annotations

from pathlib import Path

from tests.cobol.orchestrator.helpers import write_program, write_receipt


def test_agent_runs_to_completion_with_injected_rebuild(tmp_path: Path) -> None:
    from omnix.orchestrator.cobol.agent import AgentConfig, ModernizeAgent
    from omnix.orchestrator.cobol.decision_queue import TerminalDecisionQueue
    from omnix.orchestrator.cobol.run_state import RunState

    write_program(tmp_path, "HELLO")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "HELLO.in").write_bytes(b"")
    state = RunState.create(tmp_path, "python", 5.0)

    def rebuild(program, receipts_dir):
        receipt = receipts_dir / f"{program.program_id}.json"
        write_receipt(receipt, program.program_id)
        return receipt

    agent = ModernizeAgent(
        AgentConfig(tmp_path, rebuild_fn=rebuild, capture_fn=lambda *_args, **_kwargs: None, spec_gen_fn=lambda *_args, **_kwargs: None),
        run_state=state,
        decision_queue=TerminalDecisionQueue(state, input_fn=lambda _: "", output_fn=lambda _: None),
    )

    summary = agent.run()

    assert summary.verified == 1
    assert summary.audit_zip is not None and summary.audit_zip.is_file()
    state.close()


def test_agent_skips_missing_fixtures_via_decision(tmp_path: Path) -> None:
    from omnix.orchestrator.cobol.agent import AgentConfig, ModernizeAgent
    from omnix.orchestrator.cobol.decision_queue import TerminalDecisionQueue
    from omnix.orchestrator.cobol.run_state import RunState

    write_program(tmp_path, "NOFX")
    state = RunState.create(tmp_path, "python", 5.0)
    agent = ModernizeAgent(
        AgentConfig(tmp_path),
        run_state=state,
        decision_queue=TerminalDecisionQueue(state, input_fn=lambda _: "s", output_fn=lambda _: None),
    )

    summary = agent.run()

    assert summary.skipped == 1
    assert state.get_program("NOFX").state == "skipped"
    state.close()

