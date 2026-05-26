"""Tests for the codebase-memory bridge (D1 P2)."""

from __future__ import annotations

import sys
import types
from typing import Iterable

from omnix.dm.d1_schema_understanding import codebase_memory_bridge


def test_missing_module_returns_honest_note(monkeypatch):
    """When omnix.codebase_memory is not deployed we must surface that, not
    silently return empty."""
    monkeypatch.setattr(
        codebase_memory_bridge,
        "_try_import_codebase_memory",
        lambda: None,
    )
    usages, notes = codebase_memory_bridge.lookup_column_usage("owner", "email")
    assert usages == ()
    assert notes
    assert any("not deployed" in n for n in notes)


def test_module_present_returns_usages(monkeypatch):
    fake_results = [
        {
            "file_path": "app/handlers/owner.py",
            "function_name": "create_owner",
            "line_number": 42,
            "op_type": "WRITE",
        }
    ]
    monkeypatch.setattr(
        codebase_memory_bridge,
        "_try_import_codebase_memory",
        lambda: (lambda **kw: fake_results),
    )
    usages, notes = codebase_memory_bridge.lookup_column_usage("owner", "email")
    assert len(usages) == 1
    assert usages[0].file_path == "app/handlers/owner.py"
    assert usages[0].op_type == "WRITE"


def test_query_failure_surfaces_reason(monkeypatch):
    def bad_query(**kw):
        raise RuntimeError("graph offline")

    monkeypatch.setattr(
        codebase_memory_bridge,
        "_try_import_codebase_memory",
        lambda: bad_query,
    )
    usages, notes = codebase_memory_bridge.lookup_column_usage("owner", "email")
    assert usages == ()
    assert any("graph offline" in n for n in notes)


def test_column_not_in_graph_returns_empty_with_orphan_note(monkeypatch):
    monkeypatch.setattr(
        codebase_memory_bridge,
        "_try_import_codebase_memory",
        lambda: (lambda **kw: None),
    )
    usages, notes = codebase_memory_bridge.lookup_column_usage("legacy_t", "ghost")
    assert usages == ()
    assert any("orphan" in n.lower() for n in notes)
