"""Tests for the grounded Reflexion loop (P5)."""

from __future__ import annotations

from typing import List

import pytest

from omnix.dm._types import (
    ColumnMapping,
    ColumnSpec,
    PropertyDef,
    PropertySet,
    ReflexionHalt,
    ReflexionSuccess,
    SketchHint,
)
from omnix.dm.d3_transformation_synthesis import llm_synthesizer
from omnix.dm.d3_transformation_synthesis.reflexion_loop import LoopInputs, run


@pytest.fixture(autouse=True)
def _reset_backend():
    llm_synthesizer.set_llm_backend(None)
    yield
    llm_synthesizer.set_llm_backend(None)


def _col(norm="STRING", nullable=True):
    return ColumnSpec(
        name="x",
        raw_type=norm,
        normalized_type=norm,
        nullable=nullable,
        default=None,
        primary_key=False,
        unique=False,
        comment=None,
    )


def _mapping(legacy="t.x"):
    lt, lc = legacy.split(".")
    return ColumnMapping(
        legacy_table=lt,
        legacy_column=lc,
        target_table=lt,
        target_column=lc,
        confidence=0.95,
        status="ok",
    )


def _ps(props=None):
    return PropertySet(
        column_mapping_key="t.x",
        properties=props or (
            PropertyDef("type_preservation", "st.text()", "pass", None, "type"),
            PropertyDef("null_passthrough", "st.none()", "pass", None, "null"),
        ),
        coverage_complete=True,
        missing_coverage_reasons=(),
    )


def _ok_response(source="def transform(v):\n    return v\n"):
    return (
        f"```python\n{source}\n```\n"
        "```hypothesis\n@given(st.text())\ndef test_x(v): assert transform(v) is not None or v is None\n```\n"
    )


def _make_backend(responses: List[str]):
    """Return a backend that yields responses in sequence and records call args."""
    idx = {"i": 0, "calls": []}

    def _b(sys_p, usr_p, kw):
        i = idx["i"]
        idx["i"] += 1
        idx["calls"].append({"user": usr_p, "iteration": i})
        text = responses[min(i, len(responses) - 1)]
        return llm_synthesizer._BackendResponse(
            text=text, model_id="mock", prompt_tokens=1, completion_tokens=1
        )

    return _b, idx


def test_converges_in_one_iteration():
    backend, log = _make_backend([_ok_response()])
    llm_synthesizer.set_llm_backend(backend)
    out = run(
        LoopInputs(
            mapping=_mapping(),
            legacy_column=_col(),
            target_column=_col(),
            property_set=_ps(),
        )
    )
    assert isinstance(out, ReflexionSuccess)
    assert out.iterations_used == 1
    assert log["i"] == 1


def test_converges_in_three_iterations():
    """First two responses return broken transformers; third returns identity."""
    broken = "```python\ndef transform(v):\n    return 9999\n```\n```hypothesis\n# t\n```"
    backend, log = _make_backend([broken, broken, _ok_response()])
    llm_synthesizer.set_llm_backend(backend)
    out = run(
        LoopInputs(
            mapping=_mapping(),
            legacy_column=_col(norm="STRING"),
            target_column=_col(norm="STRING"),
            property_set=_ps(),
        )
    )
    # The "broken" transformer returns 9999 (int) — type_preservation will fail
    # because target is STRING. After 2 MFIs the identity passes.
    assert isinstance(out, ReflexionSuccess)
    assert out.iterations_used == 3
    assert len(out.mfi_history) == 2


def test_iteration_cap_returns_halt_with_all_mfis():
    broken = "```python\ndef transform(v):\n    return 9999\n```\n```hypothesis\n# t\n```"
    backend, _ = _make_backend([broken])
    llm_synthesizer.set_llm_backend(backend)
    out = run(
        LoopInputs(
            mapping=_mapping(),
            legacy_column=_col(norm="STRING"),
            target_column=_col(norm="STRING"),
            property_set=_ps(),
        ),
        max_iterations=5,
    )
    assert isinstance(out, ReflexionHalt)
    assert out.halt_reason == "iteration_cap"
    assert len(out.failing_mfis) == 5
    assert out.iterations_used == 5


def test_security_violation_halts_immediately():
    bad = (
        "```python\ndef transform(v): return __import__('os').system('id')\n```\n"
        "```hypothesis\n# t\n```\n"
    )
    backend, log = _make_backend([bad, _ok_response()])
    llm_synthesizer.set_llm_backend(backend)
    out = run(
        LoopInputs(
            mapping=_mapping(),
            legacy_column=_col(),
            target_column=_col(),
            property_set=_ps(),
        )
    )
    assert isinstance(out, ReflexionHalt)
    assert out.halt_reason == "security_violation"
    assert log["i"] == 1  # second response never consumed
    assert out.security_violation is not None


def test_parse_failure_halts():
    bad = "no fences here"
    backend, log = _make_backend([bad])
    llm_synthesizer.set_llm_backend(backend)
    out = run(
        LoopInputs(
            mapping=_mapping(),
            legacy_column=_col(),
            target_column=_col(),
            property_set=_ps(),
        )
    )
    assert isinstance(out, ReflexionHalt)
    assert out.halt_reason == "parse_failure"


def test_mfi_history_monotone():
    broken = "```python\ndef transform(v):\n    return 9999\n```\n```hypothesis\n# t\n```"
    backend, _ = _make_backend([broken])
    llm_synthesizer.set_llm_backend(backend)
    out = run(
        LoopInputs(
            mapping=_mapping(),
            legacy_column=_col(norm="STRING"),
            target_column=_col(norm="STRING"),
            property_set=_ps(),
        ),
        max_iterations=3,
    )
    assert isinstance(out, ReflexionHalt)
    # The history grew each iteration — never replaced.
    assert len(out.failing_mfis) == 3
    # Each MFI is distinct-ish (at least different iterations may shrink to same)
    # but the tuple must be ordered (most recent last).
    assert isinstance(out.failing_mfis, tuple)


def test_mfi_history_fed_back_into_prompt():
    broken = "```python\ndef transform(v):\n    return 9999\n```\n```hypothesis\n# t\n```"
    backend, log = _make_backend([broken])
    llm_synthesizer.set_llm_backend(backend)
    run(
        LoopInputs(
            mapping=_mapping(),
            legacy_column=_col(norm="STRING"),
            target_column=_col(norm="STRING"),
            property_set=_ps(),
        ),
        max_iterations=3,
    )
    assert log["i"] >= 2
    # Second iteration's user prompt MUST include the first MFI.
    second = log["calls"][1]["user"]
    assert "PRIOR MFI HISTORY" in second
    assert "9999" in second  # the broken output appears as actual_value_repr


def test_deterministic_with_fixed_mock():
    """Two runs with identical mock state produce identical output."""
    src = _ok_response()
    runs = []
    for _ in range(2):
        backend, _ = _make_backend([src])
        llm_synthesizer.set_llm_backend(backend)
        out = run(
            LoopInputs(
                mapping=_mapping(),
                legacy_column=_col(),
                target_column=_col(),
                property_set=_ps(),
            )
        )
        assert isinstance(out, ReflexionSuccess)
        runs.append(out.transformer_spec.python_source)
    assert runs[0] == runs[1]


def test_no_silent_identity_fallback_on_halt():
    """Even after iteration_cap, the halt does NOT carry a Success spec."""
    broken = "```python\ndef transform(v):\n    return 9999\n```\n```hypothesis\n# t\n```"
    backend, _ = _make_backend([broken])
    llm_synthesizer.set_llm_backend(backend)
    out = run(
        LoopInputs(
            mapping=_mapping(),
            legacy_column=_col(norm="STRING"),
            target_column=_col(norm="STRING"),
            property_set=_ps(),
        ),
        max_iterations=3,
    )
    assert isinstance(out, ReflexionHalt)
    # ReflexionHalt has no transformer_spec — its only output is the MFI list.
    assert not hasattr(out, "transformer_spec")


def test_loop_walltime_cap():
    src = _ok_response()
    backend, _ = _make_backend([src])
    llm_synthesizer.set_llm_backend(backend)
    out = run(
        LoopInputs(
            mapping=_mapping(),
            legacy_column=_col(),
            target_column=_col(),
            property_set=_ps(),
        ),
        max_iterations=5,
        loop_walltime_sec=0,  # immediately exceed walltime
    )
    assert isinstance(out, ReflexionHalt)
    assert out.halt_reason == "loop_walltime"
