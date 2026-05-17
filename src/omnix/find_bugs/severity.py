"""Deterministic severity scores and sort order for PBT findings."""

from __future__ import annotations

from typing import Any

from .entry_points import graph_id_for


def func_key(finding: dict[str, Any]) -> str:
    f = str(finding["file"]).replace("\\", "/")
    return graph_id_for(f, str(finding["function"]))


def compute_severity(
    finding: dict[str, Any],
    graph: dict[str, Any],
) -> int:
    """
    graph: ``caller_counts``, ``entry_reachable``, and optional ``clusters``
    keyed by ``relp::function`` (see *graph_id_for*).
    """
    fk = func_key(finding)
    ccall = graph.get("caller_counts") or {}
    ereach = graph.get("entry_reachable") or {}
    if not isinstance(ccall, dict) or not isinstance(ereach, dict):
        return 0
    caller_count = int(ccall.get(fk, 0) or 0)
    reachable = bool(ereach.get(fk, False))
    failures = finding.get("failures") or []
    failure_count = len(failures) if isinstance(failures, list) else 0
    is_public = not str(finding["function"]).startswith("_")
    return (
        (caller_count * 2)
        + (5 if reachable else 0)
        + (failure_count * 1)
        + (1 if is_public else 0)
    )


def rank_findings(
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort by descending ``severity_score``, with deterministic tiebreaks."""
    return sorted(
        findings,
        key=lambda f: (
            -int(f.get("severity_score", 0)),
            str(f.get("file", "")),
            str(f.get("function", "")),
        ),
    )
