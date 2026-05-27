"""Bulk orchestrator tests (P6) — end-to-end with mocked legacy + target."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm._types import (
    AnomalyFinding,
    ColumnMapping,
    ColumnSpec,
    SchemaSpec,
    TableSpec,
)
from omnix.dm.d4_bulk_import.consumer import ConsumedBundle
from omnix.dm.d4_bulk_import.orchestrator import (
    TargetDBInfo,
    run_bulk_import,
)


def _col(name: str, norm: str = "STRING") -> ColumnSpec:
    return ColumnSpec(
        name=name,
        raw_type=norm,
        normalized_type=norm,
        nullable=True,
        default=None,
        primary_key=name == "id",
        unique=False,
        comment=None,
    )


def _table(name: str, columns):
    return TableSpec(
        name=name,
        columns=tuple(columns),
        primary_key=("id",),
    )


def _bundle(rows_of_columns_per_table: Dict[str, List[dict]]) -> ConsumedBundle:
    tables = []
    mappings = []
    specs = {}
    spec_hashes = {}
    for tname, rows in rows_of_columns_per_table.items():
        # derive column list from first row
        col_names = list(rows[0].keys()) if rows else ["id"]
        cols = [_col(n) for n in col_names]
        tables.append(_table(tname, cols))
        for cn in col_names:
            mappings.append(
                ColumnMapping(
                    legacy_table=tname,
                    legacy_column=cn,
                    target_table=tname,
                    target_column=cn,
                    confidence=0.95,
                    status="ok",
                )
            )
            if cn != "id":  # 'id' passes through; other cols get a transformer
                src = (
                    "def transform(v):\n"
                    "    return v.upper() if isinstance(v, str) else v\n"
                )
                key = f"{tname}.{cn}"
                specs[key] = {
                    "python_source": src,
                    "column_mapping_key": key,
                }
                spec_hashes[key] = hashlib.sha256(src.encode("utf-8")).hexdigest()
    schema = SchemaSpec(dialect="postgres", name="legacy", tables=tuple(tables))
    return ConsumedBundle(
        migration_id="m1",
        column_mappings=tuple(mappings),
        findings=(),
        legacy_schema=schema,
        target_schema=schema,
        transformer_specs=specs,
        transformer_halts={},
        spec_canonical_hashes=spec_hashes,
        predecessor_hash=hashlib.sha256(b"d2").hexdigest(),
        unmapped_columns=(),
    )


# ---------------------------------------------------------------------------
# Mocked DB connections (per-table row buckets)
# ---------------------------------------------------------------------------


class _MockLegacyCursor:
    def __init__(self, rows_for_table):
        self._rows = list(rows_for_table)
        self.itersize = None

    def execute(self, sql):
        pass

    def fetchmany(self, n):
        chunk, self._rows = self._rows[:n], self._rows[n:]
        return chunk

    def close(self):
        pass


class _MockLegacyConn:
    def __init__(self, by_table):
        self._by_table = by_table  # {table_name: [tuple, ...]}

    def cursor(self, *, name=None):
        # name is f"omnix_dm_{migration}_{table}" → recover table.
        table = name.rsplit("_", 1)[-1] if name else ""
        return _MockLegacyCursor(self._by_table.get(table, []))


class _MockTargetCursor:
    def __init__(self, store):
        self.store = store
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if params is not None and "INSERT" in sql:
            self.store["rows"].append(params)

    def fetchone(self):
        return None

    def copy_expert(self, sql, buf):
        # Simulate COPY by parsing the CSV buffer
        text = buf.read()
        for line in text.splitlines():
            self.store["rows"].append(tuple(line.split(",")))


class _MockTargetConn:
    def __init__(self):
        self.store = {"rows": []}
        self.committed = False

    def cursor(self):
        return _MockTargetCursor(self.store)

    def commit(self):
        self.committed = True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def keys():
    return ml_dsa_65.keypair(seed=b"\xcc" * 48)


def _columns_dict_rows(table_data):
    """Return list of dicts in column order — _MockLegacyCursor wants tuples."""
    return table_data


def _tuples_from_dicts(dict_rows):
    """Convert list of {col: v} dicts to list of tuples in column-sort order."""
    if not dict_rows:
        return []
    cols = sorted(dict_rows[0].keys())
    return [tuple(r[c] for c in cols) for r in dict_rows]


def test_happy_path_two_tables(keys, tmp_path):
    pk, sk = keys
    rows = {
        "owners": [
            {"id": 1, "name": "alice"},
            {"id": 2, "name": "bob"},
        ],
        "pets": [{"id": 1, "name": "fido"}],
    }
    # Convert to tuples in column-sort order (matches column_names order in reader)
    # column_names = [c.name for c in columns]; columns sorted by name in our bundle.
    by_table = {t: [tuple(r[c] for c in sorted(r)) for r in rs] for t, rs in rows.items()}

    bundle = _bundle(rows)
    legacy = _MockLegacyConn(by_table)
    target = _MockTargetConn()
    result = run_bulk_import(
        bundle=bundle,
        legacy_conn=legacy,
        target_conn=target,
        legacy_dialect="postgres",
        target_dialect="postgres",
        target_db_info=TargetDBInfo("u", "h", 5432, "db"),
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
        use_copy=False,
    )
    assert result.phase == "complete"
    assert set(result.tables_complete) == {"owners", "pets"}
    assert result.total_rows_written == 3
    assert result.total_rows_quarantined == 0
    assert result.partial is False

    # BatchReceipts written
    receipts = list((tmp_path / "m1" / "d4").glob("batch-receipt-*.json"))
    assert len(receipts) == 2  # one per table (each table has 1 batch)


def test_predecessor_hash_chains_to_d2(keys, tmp_path):
    pk, sk = keys
    rows = {"owners": [{"id": 1, "name": "alice"}]}
    by_table = {t: [tuple(r[c] for c in sorted(r)) for r in rs] for t, rs in rows.items()}
    bundle = _bundle(rows)
    target = _MockTargetConn()
    run_bulk_import(
        bundle=bundle,
        legacy_conn=_MockLegacyConn(by_table),
        target_conn=target,
        legacy_dialect="postgres",
        target_dialect="postgres",
        target_db_info=TargetDBInfo("u", "h", 5432, "db"),
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
        use_copy=False,
    )
    receipt_path = next((tmp_path / "m1" / "d4").glob("batch-receipt-*.json"))
    payload = json.loads(receipt_path.read_text())
    assert payload["predecessor_hash"] == bundle.predecessor_hash


def test_target_db_fingerprint_in_receipt_not_password(keys, tmp_path):
    pk, sk = keys
    rows = {"owners": [{"id": 1, "name": "x"}]}
    by_table = {t: [tuple(r[c] for c in sorted(r)) for r in rs] for t, rs in rows.items()}
    bundle = _bundle(rows)
    info = TargetDBInfo("alice", "target.example.com", 5432, "acme")
    run_bulk_import(
        bundle=bundle,
        legacy_conn=_MockLegacyConn(by_table),
        target_conn=_MockTargetConn(),
        legacy_dialect="postgres",
        target_dialect="postgres",
        target_db_info=info,
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
        use_copy=False,
    )
    payload = json.loads(
        next((tmp_path / "m1" / "d4").glob("batch-receipt-*.json")).read_text()
    )
    fp = payload["target_db_fingerprint"]
    assert len(fp) == 64
    # No raw credentials in payload
    blob = json.dumps(payload)
    assert "password" not in blob.lower()
    assert "alice@target.example.com" not in blob


def test_empty_legacy_table_yields_no_receipts(keys, tmp_path):
    pk, sk = keys
    bundle = _bundle({"owners": [{"id": 1, "name": "x"}]})
    # Override the legacy to return zero rows
    legacy = _MockLegacyConn({"owners": []})
    result = run_bulk_import(
        bundle=bundle,
        legacy_conn=legacy,
        target_conn=_MockTargetConn(),
        legacy_dialect="postgres",
        target_dialect="postgres",
        target_db_info=TargetDBInfo("u", "h", 5432, "db"),
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
        use_copy=False,
    )
    assert result.total_rows_written == 0
    assert result.total_rows_quarantined == 0
    receipts = list((tmp_path / "m1" / "d4").glob("batch-receipt-*.json"))
    assert receipts == []
    assert "owners" in result.tables_complete


def test_checkpoint_written_after_each_batch(keys, tmp_path):
    pk, sk = keys
    rows = {"owners": [{"id": i, "name": f"u{i}"} for i in range(3)]}
    by_table = {t: [tuple(r[c] for c in sorted(r)) for r in rs] for t, rs in rows.items()}
    bundle = _bundle(rows)
    run_bulk_import(
        bundle=bundle,
        legacy_conn=_MockLegacyConn(by_table),
        target_conn=_MockTargetConn(),
        legacy_dialect="postgres",
        target_dialect="postgres",
        target_db_info=TargetDBInfo("u", "h", 5432, "db"),
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
        use_copy=False,
    )
    ckpt = tmp_path / "m1" / "d4" / "checkpoint.json"
    assert ckpt.exists()
    state = json.loads(ckpt.read_text())
    assert state["migration_id"] == "m1"
    assert "owners" in state["tables"]


def test_resume_from_checkpoint_skips_completed_batches(keys, tmp_path, monkeypatch):
    pk, sk = keys
    monkeypatch.setenv("OMNIX_DM_BULK_BATCH_SIZE", "1")
    rows = {"owners": [{"id": i, "name": f"u{i}"} for i in range(3)]}
    by_table = {t: [tuple(r[c] for c in sorted(r)) for r in rs] for t, rs in rows.items()}
    bundle = _bundle(rows)

    # First run completes
    run_bulk_import(
        bundle=bundle,
        legacy_conn=_MockLegacyConn(by_table),
        target_conn=_MockTargetConn(),
        legacy_dialect="postgres",
        target_dialect="postgres",
        target_db_info=TargetDBInfo("u", "h", 5432, "db"),
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
        use_copy=False,
    )
    first_count = len(list((tmp_path / "m1" / "d4").glob("batch-receipt-*.json")))
    assert first_count == 3

    # Second run with resume=True should re-read legacy but skip every batch.
    target2 = _MockTargetConn()
    run_bulk_import(
        bundle=bundle,
        legacy_conn=_MockLegacyConn(by_table),
        target_conn=target2,
        legacy_dialect="postgres",
        target_dialect="postgres",
        target_db_info=TargetDBInfo("u", "h", 5432, "db"),
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
        use_copy=False,
        resume=True,
    )
    # No new rows written to target (all batches skipped).
    assert len(target2.store["rows"]) == 0


def test_halted_column_excludes_table(keys, tmp_path):
    pk, sk = keys
    rows = {"owners": [{"id": 1, "name": "x"}]}
    by_table = {t: [tuple(r[c] for c in sorted(r)) for r in rs] for t, rs in rows.items()}
    bundle = _bundle(rows)
    # Add a halt receipt for owners.name so the orchestrator must skip the table.
    halts = {
        "owners.name": {
            "column_mapping_key": "owners.name",
            "halt_reason": "iteration_cap",
        }
    }
    bundle = ConsumedBundle(
        migration_id=bundle.migration_id,
        column_mappings=bundle.column_mappings,
        findings=bundle.findings,
        legacy_schema=bundle.legacy_schema,
        target_schema=bundle.target_schema,
        transformer_specs=bundle.transformer_specs,
        transformer_halts=halts,
        spec_canonical_hashes=bundle.spec_canonical_hashes,
        predecessor_hash=bundle.predecessor_hash,
        unmapped_columns=bundle.unmapped_columns,
    )
    result = run_bulk_import(
        bundle=bundle,
        legacy_conn=_MockLegacyConn(by_table),
        target_conn=_MockTargetConn(),
        legacy_dialect="postgres",
        target_dialect="postgres",
        target_db_info=TargetDBInfo("u", "h", 5432, "db"),
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
        use_copy=False,
    )
    assert "owners" in result.tables_halted
    assert result.total_rows_written == 0


def test_row_conservation_invariant(keys, tmp_path):
    """For every BatchReceipt: rows_read == rows_written + rows_quarantined."""
    pk, sk = keys
    rows = {"owners": [{"id": i, "name": f"u{i}"} for i in range(5)]}
    by_table = {t: [tuple(r[c] for c in sorted(r)) for r in rs] for t, rs in rows.items()}
    bundle = _bundle(rows)
    run_bulk_import(
        bundle=bundle,
        legacy_conn=_MockLegacyConn(by_table),
        target_conn=_MockTargetConn(),
        legacy_dialect="postgres",
        target_dialect="postgres",
        target_db_info=TargetDBInfo("u", "h", 5432, "db"),
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
        use_copy=False,
    )
    for path in (tmp_path / "m1" / "d4").glob("batch-receipt-*.json"):
        p = json.loads(path.read_text())
        assert p["rows_read"] == p["rows_written"] + p["rows_quarantined"]


def test_unmapped_column_carried_in_result(keys, tmp_path):
    pk, sk = keys
    bundle = _bundle({"owners": [{"id": 1, "name": "x"}]})
    bundle = ConsumedBundle(
        migration_id=bundle.migration_id,
        column_mappings=bundle.column_mappings,
        findings=bundle.findings,
        legacy_schema=bundle.legacy_schema,
        target_schema=bundle.target_schema,
        transformer_specs=bundle.transformer_specs,
        transformer_halts={},
        spec_canonical_hashes=bundle.spec_canonical_hashes,
        predecessor_hash=bundle.predecessor_hash,
        unmapped_columns=("owners.legacy_only_column",),
    )
    by_table = {"owners": [(1, "x")]}
    result = run_bulk_import(
        bundle=bundle,
        legacy_conn=_MockLegacyConn(by_table),
        target_conn=_MockTargetConn(),
        legacy_dialect="postgres",
        target_dialect="postgres",
        target_db_info=TargetDBInfo("u", "h", 5432, "db"),
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
        use_copy=False,
    )
    assert "owners.legacy_only_column" in result.unmapped_columns


def test_partial_true_when_quarantine_or_halts(keys, tmp_path):
    pk, sk = keys
    bundle = _bundle({"owners": [{"id": 1, "name": "x"}]})
    halts = {"owners.name": {"column_mapping_key": "owners.name", "halt_reason": "x"}}
    bundle = ConsumedBundle(
        migration_id=bundle.migration_id,
        column_mappings=bundle.column_mappings,
        findings=bundle.findings,
        legacy_schema=bundle.legacy_schema,
        target_schema=bundle.target_schema,
        transformer_specs={},
        transformer_halts=halts,
        spec_canonical_hashes={},
        predecessor_hash=bundle.predecessor_hash,
        unmapped_columns=(),
    )
    by_table = {"owners": [(1, "x")]}
    result = run_bulk_import(
        bundle=bundle,
        legacy_conn=_MockLegacyConn(by_table),
        target_conn=_MockTargetConn(),
        legacy_dialect="postgres",
        target_dialect="postgres",
        target_db_info=TargetDBInfo("u", "h", 5432, "db"),
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
        use_copy=False,
    )
    assert result.partial is True
