from __future__ import annotations

from pathlib import Path

from omnix.orchestrator.cobol.agent import AgentConfig, ModernizeAgent
from omnix.orchestrator.cobol.decision_queue import TerminalDecisionQueue
from omnix.orchestrator.cobol.run_state import RunState
from tests.cobol.graphrag.helpers import graph, mark_enriched


def test_unexpected_graphrag_exception_falls_back_to_m0_prompt(tmp_path, monkeypatch) -> None:
    store = graph(tmp_path)
    mark_enriched(store)
    state = RunState.create(tmp_path, "python", 1.0)
    seen = {}

    def boom(*args, **kwargs):
        raise RuntimeError("retrieval exploded")

    def fake_dispatch(prompt: str) -> str:
        seen["prompt"] = prompt
        return "def main(stdin: bytes) -> bytes:\n    return b''\n"

    monkeypatch.setattr("omnix.retrieval.hybrid.retrieve", boom)
    monkeypatch.setattr("omnix.orchestrator.cobol.agent._default_llm_dispatch", fake_dispatch)
    agent = ModernizeAgent(
        AgentConfig(tmp_path),
        run_state=state,
        decision_queue=TerminalDecisionQueue(state, input_fn=lambda _: "", output_fn=lambda _: None),
    )
    try:
        dispatch = agent._graphrag_dispatch(store, "prog:HELLO", "HELLO", None)
        assert "def main" in dispatch("base prompt")
        assert seen["prompt"] == "base prompt"
    finally:
        store.close()
        state.close()
