"""OMNIX-DM D3 — AI Transformation Synthesis (PR B).

Emits per-column transformers (Python lambda / SQL CASE / Datalog rule),
verified by Hypothesis property tests derived from D2 blocker manifest,
through a grounded Reflexion loop with Migrator-style CEGIS sketch hints.

Defense-in-depth security model for LLM-emitted code (CVE-2026-40217 lesson):
  1. RestrictedPython 8.1 AST-rewriting
  2. Strict allowlist of builtins + module attributes
  3. Subprocess fence with resource.setrlimit (CPU/AS/NOFILE)

See ``docs/dm/d3-transformation-synthesis.md`` for the pipeline walkthrough.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
