from __future__ import annotations

from pathlib import Path

import pytest

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


def test_agent_retries_gate6_failure_with_reflexion(tmp_path: Path) -> None:
    from omnix.orchestrator.cobol.agent import AgentConfig, ModernizeAgent
    from omnix.orchestrator.cobol.decision_queue import TerminalDecisionQueue
    from omnix.orchestrator.cobol.run_state import RunState
    from omnix.rebuild.cobol_runner import GateFailure

    write_program(tmp_path, "RETRYME")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "RETRYME.in").write_bytes(b"")
    state = RunState.create(tmp_path, "python", 5.0)
    calls = 0

    def rebuild(program, receipts_dir):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise GateFailure(
                6,
                {
                    "fixtures": 1,
                    "failures": [
                        {
                            "fixture_id": "fixture-1",
                            "legacy_stdout": "OK\n",
                            "candidate_stdout": "OK",
                        }
                    ],
                },
            )
        receipt = receipts_dir / f"{program.program_id}.json"
        write_receipt(receipt, program.program_id)
        return receipt

    agent = ModernizeAgent(
        AgentConfig(
            tmp_path,
            max_gate6_retries=2,
            rebuild_fn=rebuild,
            capture_fn=lambda *_args, **_kwargs: None,
            spec_gen_fn=lambda *_args, **_kwargs: None,
        ),
        run_state=state,
        decision_queue=TerminalDecisionQueue(state, input_fn=lambda _: "", output_fn=lambda _: None),
    )

    summary = agent.run()

    assert calls == 2
    assert summary.verified == 1
    assert state.get_program("RETRYME").gate6_attempts == 1
    state.close()


def test_agent_sets_cobcpy_for_discovered_copybooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omnix.orchestrator.cobol.agent import AgentConfig, ModernizeAgent
    from omnix.orchestrator.cobol.decision_queue import TerminalDecisionQueue
    from omnix.orchestrator.cobol.run_state import RunState

    copybooks = tmp_path / "copybooks"
    copybooks.mkdir()
    (copybooks / "CUSTREC.cpy").write_text("01 CUSTREC PIC X(10).\n", encoding="utf-8")
    write_program(tmp_path, "COPYME", copy="CUSTREC")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "COPYME.in").write_bytes(b"")
    monkeypatch.delenv("COBCPY", raising=False)
    state = RunState.create(tmp_path, "python", 5.0)
    seen_cobcpy: list[str | None] = []

    def rebuild(program, receipts_dir):
        import os

        seen_cobcpy.append(os.environ.get("COBCPY"))
        receipt = receipts_dir / f"{program.program_id}.json"
        write_receipt(receipt, program.program_id)
        return receipt

    agent = ModernizeAgent(
        AgentConfig(
            tmp_path,
            rebuild_fn=rebuild,
            capture_fn=lambda *_args, **_kwargs: None,
            spec_gen_fn=lambda *_args, **_kwargs: None,
        ),
        run_state=state,
        decision_queue=TerminalDecisionQueue(state, input_fn=lambda _: "", output_fn=lambda _: None),
    )

    agent.run()

    assert seen_cobcpy == [str(copybooks)]
    state.close()
