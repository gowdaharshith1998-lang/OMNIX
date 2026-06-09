"""Naming pivot (slice-19): company-brain UI strings — file-level assertions per AUDIT / dispatch."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def test_xrayhead_says_brain() -> None:
    t = _read("src/omnix/studio/frontend/src/components/XRayHead.tsx")
    assert "BRAIN" in t
    assert "X-RAY" not in t


def test_xraytab_says_workspace() -> None:
    t = _read("src/omnix/studio/frontend/src/components/XRayTab.tsx")
    assert 'name: "Workspace"' in t or 'name: "Workspace",' in t
    assert 'name: "Repository"' not in t


def test_scope_registry_says_workspace() -> None:
    t = _read("src/omnix/studio/frontend/src/store/scopeRegistry.ts")
    assert 'label: "Workspace"' in t
    assert 'label: "Repository"' not in t


def test_findbar_says_ask_brain() -> None:
    t = _read("src/omnix/studio/frontend/src/components/FindBar.tsx")
    assert "ASK BRAIN" in t
    assert "FIND" not in t


def test_xray_metrics_entities_connections_sources() -> None:
    t = _read("src/omnix/studio/frontend/src/components/XRayMetrics.tsx")
    assert "Entities" in t
    assert "Connections" in t
    assert "Sources" in t
    assert "Packages (tree)" not in t
    assert "Call edges" not in t
    assert "Import edges" not in t


def test_workspace_brain_data_and_stats_variant() -> None:
    t = _read("src/omnix/studio/frontend/src/components/Workspace.tsx")
    assert 'data-omnix-brain="1"' in t
    assert 'data-omnix-constellation="1"' not in t
    assert 'variant="brain"' in t
    assert 'variant="constellation"' not in t


def test_stats_panel_brain_variant() -> None:
    t = _read("src/omnix/studio/frontend/src/components/StatsPanel.tsx")
    assert '"brain"' in t
    assert "constellation" not in t.lower()


def test_codetab_empty_state_brain_copy() -> None:
    t = _read("src/omnix/studio/frontend/src/components/CodeTab.tsx")
    assert "Select an entity in the brain" in t
    assert "constellation" not in t.lower()


def test_viewer_engine_overlay_says_brain() -> None:
    t = _read("src/omnix/studio/frontend/src/components/Graph/viewerEngine.ts")
    assert "BRAIN</div>" in t or ">BRAIN</div>" in t or ">BRAIN" in t
    assert "X-RAY</div>" not in t


def test_viewer_engine_hud_says_brain_entity() -> None:
    t = _read("src/omnix/studio/frontend/src/components/Graph/viewerEngine.ts")
    assert "BRAIN · ENTITY" in t
    assert "X-RAY · SYMBOL" not in t


def test_mcp_docstrings_knowledge_language() -> None:
    t = _read("src/omnix/mcp/server.py")
    assert "knowledge graph" in t
    assert "code knowledge graph" not in t
    assert "system health" in t
    assert "code health" not in t
    assert "entity connections" in t
    assert "code connections" not in t


def test_cli_docstring_knowledge_intelligence() -> None:
    t = _read("src/omnix/cli.py")
    assert "knowledge intelligence and AXIOM provenance" in t
    assert "code intelligence and AXIOM provenance" not in t


def test_readme_locked_positioning_opening() -> None:
    """README opens with the locked positioning (graph-native legacy modernization).

    Tracks the positioning lock — PRs #35 (de0170b) + #36 (0b237b8) rewrote the README
    to a mechanism-first, dev-tool voice and shipped 'graph-native pipeline' as the
    opening positioning. The original test on commit 6ee9053 asserted
    'graph-native platform' and 'verified behavioral equivalence' as a single phrase;
    PRs #35/#36 split the value-prop into 'verified equivalence' (gate output) and
    'behavioral equivalence' (gate 6). This test is updated to match the shipped
    wording while preserving every other positioning assertion.
    """
    t = _read("README.md")
    # Positive: locked positioning is the opening sentence (PRs #35/#36 wording)
    assert "graph-native pipeline for migrating legacy systems" in t
    # Positive: the value-prop — both 'verified equivalence' and 'behavioral equivalence'
    # must appear (the README threads them: gate 6 produces behavioral equivalence,
    # which the verifier stack signs into 'verified equivalence with auditable evidence').
    assert "verified equivalence" in t
    assert "behavioral equivalence" in t
    # Negative: prior marketing positionings must not return
    assert "open-core company brain" not in t
    assert "open-core code intelligence product" not in t
    # Positive: the explicit no-overclaim disclaimer is part of the positioning
    # lock — README §"How it works" must carry it.
    assert 'Not "provable," not "100% accurate."' in t
