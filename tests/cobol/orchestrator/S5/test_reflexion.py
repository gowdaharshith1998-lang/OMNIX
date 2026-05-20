from __future__ import annotations

from pathlib import Path


def test_reflexion_extracts_byte_diff_and_refines_prompt() -> None:
    from omnix.orchestrator.cobol.reflexion import ReflexionContext, refine_prompt

    prompt = refine_prompt(
        ReflexionContext(
            original_prompt="Return ONLY Python source code.",
            failed_replica="def main(stdin): return b'bad'",
            gate6_failures=[{"fixture_id": "fx1", "legacy_stdout": "A\n", "candidate_stdout": "A"}],
        )
    )

    assert "Return ONLY Python source code." in prompt
    assert "Fixture fx1" in prompt
    assert "trailing newline" in prompt


def test_reflexion_retries_until_success() -> None:
    from omnix.orchestrator.cobol.reflexion import retry_gate6_failed

    calls: list[str] = []

    def dispatch(prompt: str) -> str:
        calls.append(prompt)
        return "def main(stdin: bytes) -> bytes:\n    return b'OK\\n'\n"

    outcome = retry_gate6_failed(
        original_prompt="base",
        original_replica="bad",
        gate_failures=[{"fixture_id": "fx", "legacy_stdout": "OK\n", "candidate_stdout": "OK"}],
        attempts_remaining=2,
        llm_dispatch=dispatch,
        validator=lambda source: None,
    )

    assert outcome.succeeded
    assert len(calls) == 1
    assert "base" in calls[0]

