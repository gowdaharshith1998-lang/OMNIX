from __future__ import annotations

from pathlib import Path

from tests.cobol.orchestrator.helpers import write_program, write_receipt


def test_retry_hooks_emit_mcts_and_ese_events(tmp_path: Path, monkeypatch) -> None:
    from omnix.evolve import ensemble_entropy
    from omnix.orchestrator.cobol.agent import AgentConfig, ModernizeAgent
    from omnix.orchestrator.cobol.decision_queue import TerminalDecisionQueue
    from omnix.orchestrator.cobol.run_state import RunState
    from omnix.rebuild.cobol_runner import GateFailure
    from omnix.traversal import thought_mcts

    write_program(tmp_path, "BOOSTME")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "BOOSTME.in").write_bytes(b"")
    monkeypatch.setenv("OMNIX_MCTS_MODE", "auto")
    monkeypatch.setenv("OMNIX_ESE_MODE", "auto")
    state = RunState.create(tmp_path, "python", 5.0)
    calls = 0
    cascade_calls = []

    def fake_search(seed_thoughts, expand_fn, evaluate_fn, budget=None):
        _ = (seed_thoughts, expand_fn, evaluate_fn, budget)
        return thought_mcts.ThoughtNode("focus on data-item padding")

    def fake_cascade(generate_fn, **kwargs):
        cascade_calls.append(kwargs)
        assert generate_fn("gpt-4.1-mini") == "OK"
        return "OK", {"stages": [{"model": "gpt-4.1-mini", "n": 1, "entropy": 0.0}]}

    monkeypatch.setattr(thought_mcts, "search", fake_search)
    monkeypatch.setattr(ensemble_entropy, "cascading_generate", fake_cascade)

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
    events = state.events()
    state.close()

    assert summary.verified == 1
    assert cascade_calls
    assert "mcts_thought_selected" in {event["kind"] for event in events}
    assert "ese_cascade_evaluated" in {event["kind"] for event in events}
