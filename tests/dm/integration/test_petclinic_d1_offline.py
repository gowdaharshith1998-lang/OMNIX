"""Offline integration-style smoke test for D1 (PR A P8).

Runs the full D1 pipeline (parse → metadata-extract w/o conn → embed → match
→ emit) against the Petclinic Oracle and PG DDL fixtures. Does NOT spin up a
live cluster — that variant requires ``OMNIX_DM_RUN_INTEGRATION=1`` and is
opt-in via the ``integration_dm`` marker (defined in pyproject).

Even without a live cluster this test exercises the cross-dialect Oracle→PG
flow end-to-end on the parser + matcher layer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm.d1_schema_understanding import (
    column_embedder,
    column_metadata,
    ddl_parser,
    mapping_emitter,
    semantic_matcher,
)
from omnix.dm.d2_edge_case_profiling import probe_planner
from omnix.dm.d2_edge_case_profiling.manifest_emitter import emit as emit_d2
from omnix.dm.receipts.ml_dsa_65_signer import verify_canonical

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_oracle_pg_d1_to_d2_offline(tmp_path):
    """Parse Oracle + PG Petclinic DDL, match columns, emit signed D1 receipt,
    plan D2 probes, emit signed D2 receipt with chain. All offline."""
    # Force deterministic embedding backend so test doesn't need HF model
    os.environ["OMNIX_DM_DISABLE_SENTENCE_TRANSFORMERS"] = "1"
    column_embedder.set_embedding_backend(column_embedder._hash_based_backend)

    oracle_ddl = (FIXTURE_DIR / "oracle_ddl.sql").read_text()
    pg_ddl = (FIXTURE_DIR / "postgres_ddl.sql").read_text()

    legacy = ddl_parser.parse(oracle_ddl, "oracle")
    target = ddl_parser.parse(pg_ddl, "postgres")
    assert hasattr(legacy, "tables"), legacy
    assert hasattr(target, "tables"), target
    assert {t.name for t in legacy.tables} >= {"owners", "pets", "visits"}
    assert {t.name for t in target.tables} >= {"owner", "pet", "visit"}

    # No live DB — extract with conn=None
    legacy_ctx = column_metadata.extract(legacy, None)
    target_ctx = column_metadata.extract(target, None)
    assert len(legacy_ctx) > 0 and len(target_ctx) > 0

    mappings = semantic_matcher.match(legacy_ctx, target_ctx)
    # Every legacy column appears in output (honesty invariant)
    assert len(mappings) == len(legacy_ctx)

    pk, sk = ml_dsa_65.keypair()
    d1_path = mapping_emitter.emit(
        mappings=mappings,
        legacy=legacy,
        target=target,
        migration_id="petclinic-offline",
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    d1_body = json.loads(d1_path.read_text(encoding="utf-8"))
    d1_sig = (d1_path.with_suffix(".json.sig")).read_text(encoding="utf-8")
    assert verify_canonical(d1_body, d1_sig, pk)

    # Plan D2 probes — at least some mappings should be probable (low_confidence
    # or ambiguous given the hash-based backend's behavior)
    plan = probe_planner.plan(mappings, legacy, max_total_cost_ms=20_000)
    # Either probed or excluded — never silently dropped
    probed_pairs = {(r.legacy_table, r.legacy_column) for r in plan.requests}
    excluded_pairs = {(t, c) for (t, c, _) in plan.excluded}
    for m in mappings:
        assert (m.legacy_table, m.legacy_column) in probed_pairs or (
            m.legacy_table,
            m.legacy_column,
        ) in excluded_pairs

    # Empty D2 results — still emits a valid manifest chained to D1
    chain_hash = (d1_path.parent / "column-mapping.chainhash").read_text(encoding="utf-8").strip()
    d2_path = emit_d2(
        results=(),
        migration_id="petclinic-offline",
        predecessor_hash=chain_hash,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    d2_body = json.loads(d2_path.read_text(encoding="utf-8"))
    d2_sig = (d2_path.with_suffix(".json.sig")).read_text(encoding="utf-8")
    assert verify_canonical(d2_body, d2_sig, pk)
    assert d2_body["predecessor_hash"] == chain_hash


@pytest.mark.integration_dm
@pytest.mark.skipif(
    os.environ.get("OMNIX_DM_RUN_INTEGRATION") != "1",
    reason="live DB integration only runs when OMNIX_DM_RUN_INTEGRATION=1",
)
def test_petclinic_live_oracle_to_postgres():
    """Placeholder for the future live-cluster integration test. Currently
    skipped by default since the OMNIX repo does not bundle Oracle/PG
    testcontainers in PR A — landing them is part of PR B's onboarding."""
    pytest.skip("live cluster integration not yet wired in this PR")
