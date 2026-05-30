"""Tests for omnix.orchestrator.retry — Phase 7 retry-with-error-context loop.

Covers requirements R-7.1..R-7.5: max 3 retries by default, gate-failure context
appended verbatim, node exhaustion does not stop sibling nodes, full attempt
history preserved for human review, retry template version unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import pytest

from omnix.gates.errors import GateCrashError
from omnix.gates.result import GateError, GateResult
from omnix.orchestrator.attempt import RebuildAttempt
from omnix.orchestrator.human_review import HumanReviewRecord, RetryRunReport
from omnix.orchestrator.retry import (
    MAX_RETRIES_DEFAULT,
    PROMPT_TEMPLATE_VERSION,
    _default_gate_runner,
    format_retry_context,
    run_with_retry,
)
from omnix.spec import DependencyRef, Identity, Signature, Spec, TypeInfo

# ---------- spec + result factories -----------------------------------------

def make_spec(fqn: str) -> Spec:
    return Spec(
        identity=Identity(fqn=fqn, kind="method", source_file=f"{fqn}.java", source_line=1),
        signature=Signature(
            canonical=f"public String {fqn.split('.')[-1]}(String)",
            modifiers=("public",),
            return_type="java.lang.String",
            param_types=("java.lang.String",),
        ),
        types=TypeInfo(
            param_types=("java.lang.String",),
            return_type="java.lang.String",
            is_return_primitive=False,
            are_params_primitive=(False,),
        ),
        dependencies=(),
        target_hints=(),
    )


def make_pass_result() -> GateResult:
    return GateResult(
        gate1_passed=True, gate2_passed=True, gate3_passed=True, gate4_passed=True
    )


def make_fail_result(*, gate: int = 1, message: str = "syntax error") -> GateResult:
    err = GateError(
        gate_number=gate,
        gate_name=f"gate{gate}_demo",
        message=message,
        details={"line": 7, "snippet": "boom"},
    )
    kwargs: dict[str, Any] = {
        "gate1_passed": True,
        "gate2_passed": True,
        "gate3_passed": True,
        "gate4_passed": True,
    }
    kwargs[f"gate{gate}_passed"] = False
    kwargs[f"gate{gate}_error"] = err
    return GateResult(**kwargs)


def make_multi_fail_result() -> GateResult:
    return GateResult(
        gate1_passed=False,
        gate2_passed=True,
        gate3_passed=False,
        gate4_passed=True,
        gate1_error=GateError(
            gate_number=1,
            gate_name="gate1_syntactic",
            message="unexpected token",
            details={"line": 3, "col": 12},
        ),
        gate3_error=GateError(
            gate_number=3,
            gate_name="gate3_signature",
            message="signature mismatch",
            details={"expected": "String foo(String)", "actual": "void foo()"},
        ),
    )


# ---------- mock dispatch + gate runner -------------------------------------

_FQN_RE = re.compile(r'"fqn":\s*"([^"]+)"')


def _extract_node_from_prompt(prompt: str) -> str:
    m = _FQN_RE.search(prompt)
    if m is None:
        raise AssertionError(f"could not extract fqn from prompt:\n{prompt[:200]}")
    return m.group(1)


class MockLLM:
    """Programmable dispatch_fn. Returns the next scripted response for the FQN
    found in the prompt and tracks per-node call counts + every prompt seen.
    """

    def __init__(self, responses_per_node: dict[str, list[str]]) -> None:
        self._scripts = responses_per_node
        self._call_counts: dict[str, int] = {}
        self.prompts_seen: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts_seen.append(prompt)
        node = _extract_node_from_prompt(prompt)
        idx = self._call_counts.get(node, 0)
        self._call_counts[node] = idx + 1
        script = self._scripts.get(node)
        if script is None:
            raise AssertionError(f"MockLLM has no script for node {node!r}")
        if idx >= len(script):
            raise AssertionError(
                f"MockLLM ran out of responses for {node!r} (asked for #{idx + 1}, have {len(script)})"
            )
        return script[idx]

    def calls_for(self, node: str) -> int:
        return self._call_counts.get(node, 0)


class MockGateRunner:
    """Programmable gate_runner. Returns the next scripted GateResult per node."""

    def __init__(self, results_per_node: dict[str, list[GateResult]]) -> None:
        self._scripts = results_per_node
        self._call_counts: dict[str, int] = {}
        self.calls: list[tuple[str, str]] = []  # (fqn, response_text)

    def __call__(self, *, spec: Spec, response_text: str, target_language: str) -> GateResult:
        fqn = spec.identity.fqn
        idx = self._call_counts.get(fqn, 0)
        self._call_counts[fqn] = idx + 1
        self.calls.append((fqn, response_text))
        script = self._scripts.get(fqn)
        if script is None:
            raise AssertionError(f"MockGateRunner has no script for node {fqn!r}")
        if idx >= len(script):
            raise AssertionError(
                f"MockGateRunner ran out for {fqn!r} (asked for #{idx + 1}, have {len(script)})"
            )
        return script[idx]


# ---------- tests ------------------------------------------------------------

def test_node_passes_on_attempt_1() -> None:
    spec = make_spec("com.x.Reverse.reverse")
    llm = MockLLM({"com.x.Reverse.reverse": ["public String reverse(String s) { return s; }"]})
    gates = MockGateRunner({"com.x.Reverse.reverse": [make_pass_result()]})

    report = run_with_retry(
        Path("/dev/null"),
        nodes=[spec],
        dispatch_fn=llm,
        gate_runner=gates,
    )

    assert report.success_count == 1
    assert report.review_count == 0
    assert report.total_attempts == 1
    assert llm.calls_for("com.x.Reverse.reverse") == 1
    only = report.successful_attempts[0]
    assert only.attempt_number == 1
    assert only.node_fqn == "com.x.Reverse.reverse"


def test_node_passes_on_attempt_3() -> None:
    spec = make_spec("com.x.Foo.bar")
    llm = MockLLM({"com.x.Foo.bar": ["v1", "v2", "v3"]})
    gates = MockGateRunner(
        {"com.x.Foo.bar": [make_fail_result(gate=1), make_fail_result(gate=2), make_pass_result()]}
    )

    report = run_with_retry(Path("/dev/null"), nodes=[spec], dispatch_fn=llm, gate_runner=gates)

    assert report.success_count == 1
    assert report.review_count == 0
    assert report.total_attempts == 3
    # The success record is the LAST attempt only (attempt 3).
    assert report.successful_attempts[0].attempt_number == 3
    # But full history retains every attempt.
    nums = [a.attempt_number for a in report.full_attempt_history]
    assert nums == [1, 2, 3]
    # Attempt 3's prompt must contain retry context (from attempt 2's failure).
    third_prompt = llm.prompts_seen[2]
    assert "## Previous attempt failed" in third_prompt
    assert "Please address each failure" in third_prompt


def test_node_exhausts_retries() -> None:
    spec = make_spec("com.x.Stub.stub")
    llm = MockLLM({"com.x.Stub.stub": ["r1", "r2", "r3"]})
    gates = MockGateRunner(
        {"com.x.Stub.stub": [make_fail_result(), make_fail_result(), make_fail_result()]}
    )

    report = run_with_retry(Path("/dev/null"), nodes=[spec], dispatch_fn=llm, gate_runner=gates)

    assert report.success_count == 0
    assert report.review_count == 1
    record = report.flagged_for_human_review[0]
    assert record.node_fqn == "com.x.Stub.stub"
    assert len(record.attempts) == MAX_RETRIES_DEFAULT == 3
    assert record.reason == "max_retries_exhausted"
    assert len(record.final_gate_errors) >= 1


def test_node_exhaustion_does_not_stop_other_nodes() -> None:
    s1, s2, s3 = make_spec("a.A.run"), make_spec("b.B.run"), make_spec("c.C.run")
    llm = MockLLM(
        {
            "a.A.run": ["r1a", "r2a", "r3a"],
            "b.B.run": ["good"],
            "c.C.run": ["good"],
        }
    )
    gates = MockGateRunner(
        {
            "a.A.run": [make_fail_result(), make_fail_result(), make_fail_result()],
            "b.B.run": [make_pass_result()],
            "c.C.run": [make_pass_result()],
        }
    )

    report = run_with_retry(Path("/dev/null"), nodes=[s1, s2, s3], dispatch_fn=llm, gate_runner=gates)

    assert report.success_count == 2
    assert report.review_count == 1
    succ_fqns = {a.node_fqn for a in report.successful_attempts}
    assert succ_fqns == {"b.B.run", "c.C.run"}
    assert report.flagged_for_human_review[0].node_fqn == "a.A.run"


def test_retry_context_format() -> None:
    spec = make_spec("x.Y.z")
    attempt = RebuildAttempt(
        node_fqn=spec.identity.fqn,
        spec_hash="dead",
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        prompt_text_hash="beef",
        response_text="garbage response",
        timestamp=RebuildAttempt.now_utc(),
        model="claude-opus-4.7",
    )
    result = make_multi_fail_result()

    ctx = format_retry_context(attempt, result)

    assert "## Previous attempt failed" in ctx
    assert "### Gate 1 failure: gate1_syntactic" in ctx
    assert "### Gate 3 failure: gate3_signature" in ctx
    assert "Please address each failure and produce a corrected version." in ctx


def test_retry_context_is_deterministic() -> None:
    spec = make_spec("a.B.c")
    attempt = RebuildAttempt(
        node_fqn=spec.identity.fqn,
        spec_hash="h1",
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        prompt_text_hash="h2",
        response_text="some prior text",
        timestamp=RebuildAttempt.now_utc(),
        model="claude-opus-4.7",
    )
    result = make_multi_fail_result()

    ctx1 = format_retry_context(attempt, result)
    ctx2 = format_retry_context(attempt, result)
    assert ctx1 == ctx2


def test_full_history_preserved_in_human_review() -> None:
    spec = make_spec("p.Q.r")
    llm = MockLLM({"p.Q.r": [f"resp{i}" for i in range(1, 4)]})
    gates = MockGateRunner({"p.Q.r": [make_fail_result(gate=i) for i in (1, 2, 3)]})

    report = run_with_retry(Path("/dev/null"), nodes=[spec], dispatch_fn=llm, gate_runner=gates)

    record = report.flagged_for_human_review[0]
    assert len(record.attempts) == 3
    assert len(record.gate_results) == 3
    nums = [a.attempt_number for a in record.attempts]
    assert nums == [1, 2, 3]
    # Responses preserved verbatim.
    assert [a.response_text for a in record.attempts] == ["resp1", "resp2", "resp3"]


def test_prompt_template_version_unchanged_across_retries() -> None:
    spec = make_spec("z.A.x")
    llm = MockLLM({"z.A.x": ["r1", "r2", "r3"]})
    gates = MockGateRunner(
        {"z.A.x": [make_fail_result(), make_fail_result(), make_pass_result()]}
    )

    report = run_with_retry(Path("/dev/null"), nodes=[spec], dispatch_fn=llm, gate_runner=gates)

    versions = {a.prompt_template_version for a in report.full_attempt_history}
    assert versions == {PROMPT_TEMPLATE_VERSION}
    # And every prompt references the same template version string.
    for p in llm.prompts_seen:
        assert f"template v{PROMPT_TEMPLATE_VERSION}" in p


def test_max_retries_configurable() -> None:
    spec = make_spec("m.N.o")
    llm = MockLLM({"m.N.o": ["only"]})
    gates = MockGateRunner({"m.N.o": [make_fail_result()]})

    report = run_with_retry(
        Path("/dev/null"),
        nodes=[spec],
        dispatch_fn=llm,
        gate_runner=gates,
        max_retries=1,
    )

    assert report.review_count == 1
    record = report.flagged_for_human_review[0]
    assert len(record.attempts) == 1


def test_dispatch_fn_exception_propagates() -> None:
    spec = make_spec("e.E.e")

    def boom(prompt: str) -> str:
        raise ConnectionError("rate limited")

    gates = MockGateRunner({"e.E.e": [make_pass_result()]})

    with pytest.raises(ConnectionError, match="rate limited"):
        run_with_retry(Path("/dev/null"), nodes=[spec], dispatch_fn=boom, gate_runner=gates)


def test_gate_crash_propagates() -> None:
    """GateCrashError raised inside gate_runner is a gate-impl bug, not a gate
    failure — it must propagate, not trigger a retry."""
    spec = make_spec("g.G.g")
    llm = MockLLM({"g.G.g": ["resp"]})

    def crashing(*, spec: Spec, response_text: str, target_language: str) -> GateResult:
        raise GateCrashError(gate_number=2, message="JVM died", original=RuntimeError("oom"))

    with pytest.raises(GateCrashError):
        run_with_retry(Path("/dev/null"), nodes=[spec], dispatch_fn=llm, gate_runner=crashing)


def test_retry_run_report_counters() -> None:
    succeeders = [make_spec(f"s.S{i}.run") for i in range(3)]
    exhausters = [make_spec(f"e.E{i}.run") for i in range(2)]

    llm_scripts: dict[str, list[str]] = {}
    gate_scripts: dict[str, list[GateResult]] = {}
    for s in succeeders:
        llm_scripts[s.identity.fqn] = ["good"]
        gate_scripts[s.identity.fqn] = [make_pass_result()]
    for s in exhausters:
        llm_scripts[s.identity.fqn] = ["r1", "r2", "r3"]
        gate_scripts[s.identity.fqn] = [make_fail_result()] * 3

    llm = MockLLM(llm_scripts)
    gates = MockGateRunner(gate_scripts)

    report = run_with_retry(
        Path("/dev/null"),
        nodes=succeeders + exhausters,
        dispatch_fn=llm,
        gate_runner=gates,
    )

    assert report.success_count == 3
    assert report.review_count == 2
    # 3 successes * 1 attempt + 2 exhausters * 3 attempts = 9
    assert report.total_attempts == 3 + 2 * 3


def test_attempt_numbers_are_monotone_per_node() -> None:
    """Sibling: ensures attempt_number increments 1..N within a node even when
    interleaved with other nodes."""
    s1, s2 = make_spec("a.A.x"), make_spec("b.B.y")
    llm = MockLLM(
        {
            "a.A.x": ["r1", "r2"],
            "b.B.y": ["ok"],
        }
    )
    gates = MockGateRunner(
        {
            "a.A.x": [make_fail_result(), make_pass_result()],
            "b.B.y": [make_pass_result()],
        }
    )
    report = run_with_retry(Path("/dev/null"), nodes=[s1, s2], dispatch_fn=llm, gate_runner=gates)
    a_nums = [a.attempt_number for a in report.full_attempt_history if a.node_fqn == "a.A.x"]
    assert a_nums == [1, 2]
    b_nums = [a.attempt_number for a in report.full_attempt_history if a.node_fqn == "b.B.y"]
    assert b_nums == [1]


def test_max_retries_invalid_raises() -> None:
    spec = make_spec("z.Z.z")
    with pytest.raises(ValueError):
        run_with_retry(
            Path("/dev/null"),
            nodes=[spec],
            dispatch_fn=lambda p: "x",
            gate_runner=lambda **_: make_pass_result(),
            max_retries=0,
        )


def test_default_gate_runner_bridges_to_runner_and_returns_gate_result() -> None:
    """The default gate runner adapts (spec, response_text, target_language) to
    gates.runner.run and returns a populated GateResult — guards the bridge that
    previously called run() with a stale signature (would raise TypeError)."""
    spec = make_spec("com.x.Reverse.reverse")
    result = _default_gate_runner(
        spec,
        response_text="public String reverse(String s) { return s; }",
        target_language="java21",
    )
    assert isinstance(result, GateResult)
    # All four gate verdicts are populated booleans (gates ran; nothing crashed).
    for passed in (
        result.gate1_passed,
        result.gate2_passed,
        result.gate3_passed,
        result.gate4_passed,
    ):
        assert isinstance(passed, bool)
