from __future__ import annotations

from pathlib import Path
from typing import Any

from omnix.evolve.skill_bank import SkillBank
from omnix.orchestrator.cobol.agent import AgentConfig, ModernizeAgent
from omnix.orchestrator.cobol.decision_queue import TerminalDecisionQueue
from omnix.orchestrator.cobol.run_state import RunState
from tests.cobol.orchestrator.helpers import write_program, write_receipt


def test_orchestrator_rolls_back_regressed_skills_after_sidecar_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    write_program(tmp_path, "HELLO")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "HELLO.in").write_bytes(b"")
    state = RunState.create(tmp_path, "python", 1.0)
    calls: list[Path | None] = []

    def fake_rebuild(program, receipts_dir):
        receipt = receipts_dir / f"{program.program_id}.json"
        write_receipt(receipt, program.program_id)
        return receipt

    def fake_rollback(self: SkillBank, graph_store, **kwargs: Any) -> list[str]:
        calls.append(kwargs.get("runs_dir"))
        return ["skill-risk"]

    monkeypatch.setattr(SkillBank, "auto_rollback_on_regression", fake_rollback)
    agent = ModernizeAgent(
        AgentConfig(
            tmp_path,
            rebuild_fn=fake_rebuild,
            capture_fn=lambda *_args, **_kwargs: None,
            spec_gen_fn=lambda *_args, **_kwargs: None,
        ),
        run_state=state,
        decision_queue=TerminalDecisionQueue(state, input_fn=lambda _: "", output_fn=lambda _: None),
    )
    agent._graphrag_contexts["HELLO"] = {
        "target_node_id": "prog:HELLO",
        "node_ids": ["prog:HELLO"],
        "retrieval_modes": {"vector": 1},
        "skills_applied": [{"skill_id": "skill-risk", "version": 1, "t_valid": "now"}],
        "token_cost": {},
        "enrichment_data_hash": "abc",
    }

    try:
        summary = agent.run()
        events = state.events()
    finally:
        state.close()

    assert summary.verified == 1
    assert calls == [state.run_dir.parent]
    assert any(event["kind"] == "skill_rolled_back" for event in events)


def test_orchestrator_does_not_fail_rebuild_when_rollback_check_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    write_program(tmp_path, "HELLO")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "HELLO.in").write_bytes(b"")
    state = RunState.create(tmp_path, "python", 1.0)

    def fake_rebuild(program, receipts_dir):
        receipt = receipts_dir / f"{program.program_id}.json"
        write_receipt(receipt, program.program_id)
        return receipt

    def fake_rollback(self: SkillBank, graph_store, **kwargs: Any) -> list[str]:
        raise RuntimeError("metric read failed")

    monkeypatch.setattr(SkillBank, "auto_rollback_on_regression", fake_rollback)
    agent = ModernizeAgent(
        AgentConfig(
            tmp_path,
            rebuild_fn=fake_rebuild,
            capture_fn=lambda *_args, **_kwargs: None,
            spec_gen_fn=lambda *_args, **_kwargs: None,
        ),
        run_state=state,
        decision_queue=TerminalDecisionQueue(state, input_fn=lambda _: "", output_fn=lambda _: None),
    )
    agent._graphrag_contexts["HELLO"] = {
        "target_node_id": "prog:HELLO",
        "node_ids": ["prog:HELLO"],
        "retrieval_modes": {"vector": 1},
        "skills_applied": [{"skill_id": "skill-risk", "version": 1, "t_valid": "now"}],
        "token_cost": {},
        "enrichment_data_hash": "abc",
    }

    try:
        summary = agent.run()
        events = state.events()
    finally:
        state.close()

    assert summary.verified == 1
    assert any(event["kind"] == "skill_rollback_error" for event in events)
