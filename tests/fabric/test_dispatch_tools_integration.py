from __future__ import annotations

from pathlib import Path
from typing import Any

from omnix.fabric.dispatch_tools import dispatch_with_tools
from omnix.graph.store import GraphStore
from omnix.providers.tools import ToolContext


def test_dispatch_multi_turn_mock_client_executes_tool_then_finishes(
    tmp_path: Path,
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    store = GraphStore(str(tmp_path / "graph.db"))
    store.add_node("a.py::foo", "foo", "function", "a.py", 1, 5)
    store.commit()
    ctx = ToolContext(
        workspace_id="w",
        project_id="p",
        project_root=project,
        store=store,
    )

    class _SeqClient:
        provider = "openai"
        n = 0

        def chat(
            self,
            messages: list[dict[str, Any]],
            model: str | None = None,
            **kwargs: Any,
        ) -> dict[str, Any]:
            self.n += 1
            if self.n == 1:
                return {
                    "ok": True,
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "get_node_context",
                                "arguments": '{"node_id": "a.py::foo"}',
                            },
                        }
                    ],
                    "usage": {"tokens_in": 10, "tokens_out": 5},
                }
            return {
                "ok": True,
                "content": "The function foo is defined in a.py.",
                "tool_calls": None,
                "usage": {"tokens_in": 20, "tokens_out": 15},
            }

    client = _SeqClient()
    result = dispatch_with_tools(
        client,
        messages=[{"role": "user", "content": "Explain foo"}],
        model="gpt-4o",
        tools=["get_node_context"],
        tool_context=ctx,
        tool_args=None,
        provider_override="openai",
    )
    assert result.get("ok") is True
    assert "foo" in str(result.get("content", ""))
    steps = result.get("tool_steps") or []
    assert len(steps) >= 1
    assert any(s.get("tool") == "get_node_context" for s in steps)
    assert int(result.get("iterations") or 0) >= 1
    store.close()


def test_dispatch_prefetch_only_google_no_tool_definitions(
    tmp_path: Path,
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    store = GraphStore(str(tmp_path / "g.db"))
    store.commit()
    ctx = ToolContext(
        workspace_id="w",
        project_id="p",
        project_root=project,
        store=store,
    )
    seen: dict[str, Any] = {}

    class _GClient:
        provider = "google"

        def chat(
            self,
            messages: list[dict[str, Any]],
            model: str | None = None,
            **kwargs: Any,
        ) -> dict[str, Any]:
            seen.update(kwargs)
            return {
                "ok": True,
                "content": "ok",
                "usage": {"tokens_in": 1, "tokens_out": 1},
            }

    c = _GClient()
    dispatch_with_tools(
        c,
        messages=[{"role": "user", "content": "x"}],
        model=None,
        tools=["get_node_context"],
        tool_context=ctx,
        tool_args=None,
        provider_override="google",
    )
    assert "tool_definitions" not in seen
    store.close()


def test_dispatch_max_iterations_caps(tmp_path: Path, monkeypatch: Any) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    store = GraphStore(str(tmp_path / "g2.db"))
    store.commit()
    ctx = ToolContext(
        workspace_id="w",
        project_id="p",
        project_root=project,
        store=store,
    )

    class _LoopClient:
        provider = "openai"

        def chat(
            self,
            messages: list[dict[str, Any]],
            model: str | None = None,
            **kwargs: Any,
        ) -> dict[str, Any]:
            return {
                "ok": True,
                "content": "",
                "tool_calls": [
                    {
                        "id": "x",
                        "type": "function",
                        "function": {
                            "name": "get_node_context",
                            "arguments": "{}",
                        },
                    }
                ],
                "usage": {"tokens_in": 1, "tokens_out": 1},
            }

    monkeypatch.setattr(
        "src.fabric.dispatch_tools.MAX_ITERATIONS",
        2,
        raising=False,
    )
    out = dispatch_with_tools(
        _LoopClient(),
        messages=[{"role": "user", "content": "x"}],
        model=None,
        tools=["get_node_context"],
        tool_context=ctx,
        tool_args=None,
        provider_override="openai",
    )
    assert out.get("capped") is True
    assert out.get("cap_reason") == "max_iterations"
    store.close()
