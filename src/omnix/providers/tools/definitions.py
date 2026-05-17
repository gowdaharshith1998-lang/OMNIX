"""Provider-shaped tool definitions for LLM function calling (slice 15.3.7)."""

from __future__ import annotations

import json
from typing import Any, Literal

ToolShape = Literal["openai", "anthropic"]

# Rich descriptions: what, when, arg format with e.g., return shape.
_TOOL_META: dict[str, dict[str, Any]] = {
    "get_node_context": {
        "description": (
            "Load graph metadata for a single symbol (node): type, file path, line range, "
            "complexity, and a slice of edges touching this node. "
            "Use this first to anchor follow-up questions about a specific function or class. "
            "Returns JSON with `node` (or null if unknown id) and `edges` (relationships). "
            "Empty edge list still tells you the symbol exists in isolation. "
            "\n\n"
            "Argument format: node_id is `path/to/file.py::symbol_name` for top-level functions, "
            "or `path/file.py::ClassName.method` for methods (matches OMNIX graph node ids). "
            "Example: node_id='src/auth/login.py::authenticate_user'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": (
                        "Symbol id as 'path/to/file.py::name' (e.g. 'src/auth.py::login'). "
                        "Must match a node id from the OMNIX graph."
                    ),
                }
            },
            "required": ["node_id"],
        },
    },
    "find_callers": {
        "description": (
            "Find all functions/methods that call a given symbol (incoming CALLS edges). "
            "Use this to understand impact before suggesting changes to a function. "
            "Returns a list of caller nodes with file paths and line numbers. "
            "An empty list means the symbol has no callers in this codebase snapshot. "
            "\n\n"
            "Argument format: node_id is 'path/to/file.py::function_name' or "
            "'path/file.py::ClassName.method_name'. "
            "Example: node_id='src/auth/login.py::authenticate_user'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "Symbol identifier as 'path/to/file.py::name'",
                }
            },
            "required": ["node_id"],
        },
    },
    "find_callees": {
        "description": (
            "Find symbols this function/method calls (outgoing CALLS edges). "
            "Use this to trace dependencies and complexity from a starting symbol. "
            "Returns callees with file paths and types. "
            "\n\n"
            "Argument format: node_id as for other tools, e.g. "
            "node_id='src/api/handlers.py::process_payment'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "Symbol identifier as 'path/to/file.py::name'",
                }
            },
            "required": ["node_id"],
        },
    },
    "find_related_files": {
        "description": (
            "List other files linked to a file or symbol via graph edges (imports, calls, etc.). "
            "Use this to see coupling between modules. "
            "Returns per-file summaries with relationship types and sample nodes. "
            "\n\n"
            "Arguments: file_path is project-relative (e.g. 'src/auth.py'). "
            "Optionally pass node_id to focus on one symbol within that file. "
            "Example: file_path='src/auth.py', node_id='src/auth.py::login'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Project-relative path to a source file",
                },
                "node_id": {
                    "type": "string",
                    "description": "Optional symbol id to narrow scope",
                },
            },
            "required": [],
        },
    },
    "read_code_region": {
        "description": (
            "Read a slice of source text from a project file by line range. "
            "Use this to quote or inspect implementation details not fully captured in the graph. "
            "Returns JSON with file_path, line_start, line_end, and `text` snippet. "
            "Large regions may be truncated server-side. "
            "\n\n"
            "Arguments: file_path project-relative; line_start and line_end are 1-based inclusive. "
            "Example: file_path='src/auth.py', line_start=45, line_end=78"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Project-relative file path",
                },
                "line_start": {
                    "type": "integer",
                    "description": "Start line (1-based)",
                },
                "line_end": {
                    "type": "integer",
                    "description": "End line (1-based, inclusive)",
                },
            },
            "required": ["file_path"],
        },
    },
}


def build_tool_definitions(
    tool_names: list[str],
    shape: ToolShape,
) -> list[dict[str, Any]]:
    """Build OpenAI or Anthropic tool list entries for the given tool names."""
    out: list[dict[str, Any]] = []
    for raw in tool_names:
        name = str(raw)
        if name not in _TOOL_META:
            continue
        meta = _TOOL_META[name]
        desc = str(meta["description"])
        params = meta["parameters"]
        if shape == "openai":
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": desc,
                        "parameters": params,
                    },
                }
            )
        else:
            out.append(
                {
                    "name": name,
                    "description": desc,
                    "input_schema": params,
                }
            )
    return out


def summarize_tool_args(name: str, args: dict[str, Any]) -> str:
    """Short human-readable summary for UI (~80 chars)."""
    keys = ("node_id", "file_path", "line_start", "line_end", "path")
    parts: list[str] = []
    for k in keys:
        v = args.get(k)
        if v is not None and v != "":
            s = str(v)
            if len(s) > 40:
                s = s[:37] + "..."
            parts.append(f"{k}={s}")
    if not parts:
        try:
            raw = json.dumps(args, sort_keys=True)
        except (TypeError, ValueError):
            raw = str(args)
        return raw[:80] + ("..." if len(raw) > 80 else "")
    summary = ", ".join(parts)
    return summary[:80] + ("..." if len(summary) > 80 else "")


def tool_shape_for_provider(provider: str) -> ToolShape:
    """Map fabric provider id to tool definition shape."""
    if provider == "anthropic":
        return "anthropic"
    return "openai"
