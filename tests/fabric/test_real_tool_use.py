# CLASSIFICATION: MIXED — 3 PASSING (tool definition shapes), 2 XFAIL (openai_compatible.call lacks `tools` param; dispatcher lacks _tool_use_message_list)
from __future__ import annotations

import pytest

from omnix.providers.tools.definitions import build_tool_definitions, summarize_tool_args


def test_build_tool_definitions_openai_shape() -> None:
    defs = build_tool_definitions(["get_node_context"], "openai")
    assert len(defs) == 1
    assert defs[0]["type"] == "function"
    assert defs[0]["function"]["name"] == "get_node_context"
    assert "parameters" in defs[0]["function"]


def test_build_tool_definitions_anthropic_shape() -> None:
    defs = build_tool_definitions(["find_callers"], "anthropic")
    assert len(defs) == 1
    assert defs[0]["name"] == "find_callers"
    assert "input_schema" in defs[0]


def test_summarize_tool_args_truncates() -> None:
    s = summarize_tool_args(
        "find_callers",
        {"node_id": "src/very/long/path/to/file.py::some_symbol_name_here"},
    )
    assert "node_id=" in s
    assert len(s) <= 80


@pytest.mark.xfail(
    strict=True,
    reason=(
        "slice 15.3.7 LLM tool-dispatch: omnix.fabric.providers.openai_compatible.call() "
        "does not yet accept a `tools` parameter. Test is the spec for the slice 15.3.7 "
        "tools-param API surface. Tracked as a known pre-M1 limitation. "
        "[Outside M1 finisher Phase 4-7 scope — separate slice-15.3.7 work stream.]"
    ),
)
def test_openai_compatible_accepts_tools_parameter() -> None:
    import inspect

    from omnix.fabric.providers import openai_compatible

    sig = inspect.signature(openai_compatible.call)
    assert "tools" in sig.parameters


@pytest.mark.xfail(
    strict=True,
    reason=(
        "slice 15.3.7 LLM tool-dispatch: omnix.fabric.dispatcher has no "
        "_tool_use_message_list helper yet. Test is the spec for the orchestrator's "
        "tool-use message construction. Tracked as a known pre-M1 limitation. "
        "[Outside M1 finisher Phase 4-7 scope — separate slice-15.3.7 work stream.]"
    ),
)
def test_dispatcher_has_tool_definitions_option_path() -> None:
    import inspect

    from omnix.fabric import dispatcher

    assert hasattr(dispatcher, "_tool_use_message_list")
