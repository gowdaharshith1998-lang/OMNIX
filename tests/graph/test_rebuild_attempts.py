"""GraphStore rebuild_attempts table — M1 finisher Phase 5 additive schema.

Covers the storage path the M1 orchestrator + Phase 6 receipt emitter rely
on: store one or more RebuildAttempt rows per node, retrieve them in
attempt-order, and verify the migration is idempotent / additive.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnix.graph.store import GraphStore


@pytest.fixture
def store(tmp_path: Path):
    s = GraphStore(str(tmp_path / "rebuild.db"))
    try:
        yield s
    finally:
        s.close()


def _stamp(node_fqn: str, *, attempt_number: int = 1, suffix: str = "") -> dict:
    """Build a kwargs dict for store_rebuild_attempt."""
    return {
        "node_fqn": node_fqn,
        "spec_hash": f"specsha{suffix}",
        "prompt_template_version": "v1-2026-05-17",
        "prompt_text_hash": f"prompt{suffix}",
        "response_text": f"public class T {{ /* rebuild {suffix} */ }}",
        "timestamp": f"2026-05-17T10:00:0{attempt_number}Z",
        "model": "claude-opus-4.7",
        "attempt_number": attempt_number,
    }


def test_rebuild_attempts_table_created_on_first_access(store: GraphStore) -> None:
    """R-5.2 — table exists immediately, no explicit migration call needed."""
    rows = store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rebuild_attempts'"
    ).fetchall()
    assert len(rows) == 1


def test_indexes_created(store: GraphStore) -> None:
    rows = store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND name IN ('idx_rebuild_attempts_node_fqn', 'idx_rebuild_attempts_node_attempt')"
    ).fetchall()
    assert {r[0] for r in rows} == {
        "idx_rebuild_attempts_node_fqn",
        "idx_rebuild_attempts_node_attempt",
    }


def test_store_rebuild_attempt_returns_positive_rowid(store: GraphStore) -> None:
    rowid = store.store_rebuild_attempt(**_stamp("org.example.Foo.bar"))
    assert rowid > 0


def test_get_rebuild_attempts_returns_stored_row(store: GraphStore) -> None:
    store.store_rebuild_attempt(**_stamp("org.example.Foo.bar"))
    rows = store.get_rebuild_attempts("org.example.Foo.bar")
    assert len(rows) == 1
    row = rows[0]
    assert row["node_fqn"] == "org.example.Foo.bar"
    assert row["spec_hash"] == "specsha"
    assert row["prompt_template_version"] == "v1-2026-05-17"
    assert row["model"] == "claude-opus-4.7"
    assert row["attempt_number"] == 1


def test_get_rebuild_attempts_returns_empty_for_unknown_fqn(store: GraphStore) -> None:
    assert store.get_rebuild_attempts("does.not.exist") == []


def test_multiple_attempts_for_same_node_ordered_by_attempt_number(
    store: GraphStore,
) -> None:
    store.store_rebuild_attempt(**_stamp("org.example.Foo.bar", attempt_number=2, suffix="-2"))
    store.store_rebuild_attempt(**_stamp("org.example.Foo.bar", attempt_number=1, suffix="-1"))
    store.store_rebuild_attempt(**_stamp("org.example.Foo.bar", attempt_number=3, suffix="-3"))

    rows = store.get_rebuild_attempts("org.example.Foo.bar")
    assert [r["attempt_number"] for r in rows] == [1, 2, 3]
    assert [r["spec_hash"] for r in rows] == ["specsha-1", "specsha-2", "specsha-3"]


def test_attempts_isolated_by_node_fqn(store: GraphStore) -> None:
    store.store_rebuild_attempt(**_stamp("org.example.Foo.bar"))
    store.store_rebuild_attempt(**_stamp("org.example.Foo.baz"))
    bar_rows = store.get_rebuild_attempts("org.example.Foo.bar")
    baz_rows = store.get_rebuild_attempts("org.example.Foo.baz")
    assert len(bar_rows) == 1
    assert len(baz_rows) == 1
    assert bar_rows[0]["node_fqn"] == "org.example.Foo.bar"
    assert baz_rows[0]["node_fqn"] == "org.example.Foo.baz"


def test_migration_is_idempotent(tmp_path: Path) -> None:
    """R-5.5 invariant — re-opening the DB doesn't break the schema."""
    db_path = str(tmp_path / "rebuild.db")
    s1 = GraphStore(db_path)
    rowid1 = s1.store_rebuild_attempt(**_stamp("org.example.Foo.bar"))
    s1.close()

    s2 = GraphStore(db_path)
    rowid2 = s2.store_rebuild_attempt(**_stamp("org.example.Foo.bar", suffix="-2"))
    rows = s2.get_rebuild_attempts("org.example.Foo.bar")
    s2.close()

    assert rowid2 > rowid1
    assert len(rows) == 2


def test_migration_additive_existing_node_tables_untouched(store: GraphStore) -> None:
    """R-5.5 — existing nodes/edges tables must not have been modified."""
    store.add_node("n1", "name1", "function", file_path="foo.py")
    assert store.node_count() == 1
    # Adding a rebuild attempt for an unrelated FQN doesn't touch nodes table.
    store.store_rebuild_attempt(**_stamp("does.not.match.any.node"))
    assert store.node_count() == 1
    assert len(store.get_all_nodes()) == 1
