from __future__ import annotations

from decimal import Decimal

from click.testing import CliRunner

from omnix.cli import main


def test_accuracy_boost_sets_env_only_during_modernize_run(tmp_path, monkeypatch) -> None:
    import omnix.orchestrator.cobol.agent as agent_mod

    seen_env = {}

    class FakeAgent:
        def __init__(self, config, *, run_state, decision_queue) -> None:
            self.run_state = run_state
            self.config = config
            _ = decision_queue

        def run(self):
            for key in (
                "OMNIX_CHUNK_MODE",
                "OMNIX_GRAPHRAG_RERANK_MODE",
                "OMNIX_MCTS_MODE",
                "OMNIX_ESE_MODE",
            ):
                seen_env[key] = __import__("os").environ.get(key)
            return agent_mod.AgentSummary(
                run_id=self.run_state.run_id,
                verified=1,
                gate6_failed=0,
                skipped=0,
                errored=0,
                total_spend_usd=Decimal("0"),
                elapsed_seconds=0.0,
                receipts_dir=self.run_state.run_dir / "receipts",
                audit_zip=None,
            )

    for key in (
        "OMNIX_CHUNK_MODE",
        "OMNIX_GRAPHRAG_RERANK_MODE",
        "OMNIX_MCTS_MODE",
        "OMNIX_ESE_MODE",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(agent_mod, "ModernizeAgent", FakeAgent)

    result = CliRunner().invoke(main, ["cobol", "modernize", str(tmp_path), "--accuracy-boost", "--no-auto-audit"])

    assert result.exit_code == 0, result.output
    assert seen_env == {
        "OMNIX_CHUNK_MODE": "auto",
        "OMNIX_GRAPHRAG_RERANK_MODE": "auto",
        "OMNIX_MCTS_MODE": "auto",
        "OMNIX_ESE_MODE": "auto",
    }
    assert __import__("os").environ.get("OMNIX_CHUNK_MODE") is None
