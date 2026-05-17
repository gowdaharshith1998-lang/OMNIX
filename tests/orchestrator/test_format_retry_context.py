"""Tests for omnix.orchestrator.retry.format_retry_context.

Per R-7.4 the context block must:
- Render a stable header ("## Previous attempt failed")
- Render one section per failed gate with structured details
- Render a trailing instruction line so the LLM knows to address each failure
- Be deterministic — same inputs, byte-identical output
- Include a bounded excerpt of the prior response so the LLM can see what it produced
"""

from __future__ import annotations

from omnix.gates.result import GateError, GateResult
from omnix.orchestrator.attempt import RebuildAttempt
from omnix.orchestrator.retry import (
    PROMPT_TEMPLATE_VERSION,
    RESPONSE_EXCERPT_CHARS,
    format_retry_context,
)


def _make_attempt(response: str = "prior response body") -> RebuildAttempt:
    return RebuildAttempt(
        node_fqn="x.Y.z",
        spec_hash="spec",
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        prompt_text_hash="prompt",
        response_text=response,
        timestamp=RebuildAttempt.now_utc(),
        model="claude-opus-4.7",
    )


def _result_with(*errors: GateError) -> GateResult:
    # Place each error in its matching slot; flip only those gates to failed.
    kwargs = {
        "gate1_passed": True, "gate2_passed": True, "gate3_passed": True, "gate4_passed": True,
        "gate1_error": None, "gate2_error": None, "gate3_error": None, "gate4_error": None,
    }
    for err in errors:
        kwargs[f"gate{err.gate_number}_passed"] = False
        kwargs[f"gate{err.gate_number}_error"] = err
    return GateResult(**kwargs)


def test_single_gate_failure_renders_correctly() -> None:
    err = GateError(
        gate_number=1,
        gate_name="gate1_syntactic",
        message="missing semicolon",
        details={"line": 12, "col": 4},
    )
    ctx = format_retry_context(_make_attempt(), _result_with(err))

    assert "## Previous attempt failed" in ctx
    assert "### Gate 1 failure: gate1_syntactic" in ctx
    assert "Message: missing semicolon" in ctx
    assert "line: 12" in ctx
    assert "col: 4" in ctx
    assert "Please address each failure and produce a corrected version." in ctx


def test_multiple_gate_failures_render_with_separator() -> None:
    e1 = GateError(gate_number=1, gate_name="gate1_syntactic", message="bad token", details={})
    e3 = GateError(gate_number=3, gate_name="gate3_signature", message="sig mismatch", details={})
    ctx = format_retry_context(_make_attempt(), _result_with(e1, e3))

    assert "### Gate 1 failure: gate1_syntactic" in ctx
    assert "### Gate 3 failure: gate3_signature" in ctx
    # The two sections should be separated by at least one blank line.
    g1_idx = ctx.index("### Gate 1")
    g3_idx = ctx.index("### Gate 3")
    between = ctx[g1_idx:g3_idx]
    assert "\n\n" in between


def test_error_details_dict_included_human_readably() -> None:
    err = GateError(
        gate_number=3,
        gate_name="gate3_signature",
        message="signature mismatch",
        details={"expected": "String foo(String)", "actual": "void foo()"},
    )
    ctx = format_retry_context(_make_attempt(), _result_with(err))

    assert "Details:" in ctx
    assert "expected: String foo(String)" in ctx
    assert "actual: void foo()" in ctx


def test_empty_errors_tuple_still_produces_header_and_footer() -> None:
    """Degenerate case: no gates flagged errors but result.passed is False
    somehow (shouldn't happen in practice — every failing gate must attach an
    error). The function must not crash and must still produce a well-formed
    context block. Policy: emit header + footer, no per-gate sections.
    """
    result = GateResult(gate1_passed=True, gate2_passed=True, gate3_passed=True, gate4_passed=True)
    assert result.errors == ()
    ctx = format_retry_context(_make_attempt(), result)

    assert "## Previous attempt failed" in ctx
    assert "Please address each failure and produce a corrected version." in ctx
    assert "### Gate" not in ctx  # no per-gate sections


def test_deterministic_across_two_calls() -> None:
    err = GateError(
        gate_number=2,
        gate_name="gate2_typecheck",
        message="symbol not found",
        details={"symbol": "Foo", "scope": "method"},
    )
    attempt = _make_attempt("some response text")
    result = _result_with(err)

    ctx1 = format_retry_context(attempt, result)
    ctx2 = format_retry_context(attempt, result)
    assert ctx1 == ctx2


def test_details_keys_sorted_for_determinism() -> None:
    """Insertion-order dicts could leak nondeterminism into hashed prompts. The
    formatter sorts keys to guarantee a stable byte stream."""
    err_a = GateError(
        gate_number=4,
        gate_name="gate4_dependency",
        message="dep mismatch",
        details={"zeta": 1, "alpha": 2, "mu": 3},
    )
    err_b = GateError(
        gate_number=4,
        gate_name="gate4_dependency",
        message="dep mismatch",
        details={"alpha": 2, "mu": 3, "zeta": 1},
    )
    ctx_a = format_retry_context(_make_attempt(), _result_with(err_a))
    ctx_b = format_retry_context(_make_attempt(), _result_with(err_b))
    assert ctx_a == ctx_b


def test_response_excerpt_is_bounded() -> None:
    long_response = "X" * (RESPONSE_EXCERPT_CHARS * 5)
    ctx = format_retry_context(
        _make_attempt(long_response),
        _result_with(
            GateError(gate_number=1, gate_name="g1", message="m", details={}),
        ),
    )
    # The full long string must NOT appear; the excerpt is capped.
    assert long_response not in ctx
    # The bounded excerpt must appear.
    assert "X" * RESPONSE_EXCERPT_CHARS in ctx
    # And it must be exactly the cap, not longer.
    assert "X" * (RESPONSE_EXCERPT_CHARS + 1) not in ctx


def test_response_excerpt_label_is_present() -> None:
    """The excerpt is labelled so the LLM knows what it's looking at."""
    ctx = format_retry_context(
        _make_attempt("hello world"),
        _result_with(
            GateError(gate_number=1, gate_name="g1", message="m", details={}),
        ),
    )
    assert f"Previous response (first {RESPONSE_EXCERPT_CHARS} chars):" in ctx
    assert "hello world" in ctx
