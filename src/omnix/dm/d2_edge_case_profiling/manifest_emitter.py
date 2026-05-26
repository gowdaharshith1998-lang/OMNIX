"""D2 edge-case manifest emitter.

Aggregates ProbeResults into the ``edge-case-manifest.json`` document, signs
with ML-DSA-65, and writes atomically. The manifest's ``predecessor_hash``
MUST chain to the D1 ``column-mapping.json`` SHA-256.
"""

from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path
from typing import Optional, Tuple

from jsonschema import Draft202012Validator

from omnix.crypto import ml_dsa_65
from omnix.dm._types import AnomalyFinding, ProbeResult
from omnix.dm.receipts import merkle_chain
from omnix.dm.receipts.ml_dsa_65_signer import sign_canonical
from omnix.dm.receipts.schemas import EDGE_CASE_MANIFEST_SCHEMA


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _finding_to_dict(f: AnomalyFinding) -> dict:
    return {
        "probe_category": f.probe_category,
        "legacy_table": f.legacy_table,
        "legacy_column": f.legacy_column,
        "anomaly_type": f.anomaly_type,
        "severity": f.severity,
        "sample_values": list(f.sample_values),
        "affected_row_count": f.affected_row_count,
        "remediation_hint": f.remediation_hint,
        "requires_human_decision": f.requires_human_decision,
    }


def _atomic_write(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)


def build_manifest(
    results: Tuple[ProbeResult, ...],
    migration_id: str,
    predecessor_hash: str,
    public_key: bytes,
) -> dict:
    findings: list[dict] = []
    failures: list[dict] = []
    blocker_count = warn_count = info_count = 0
    timeout_count = error_count = 0

    for r in results:
        if r.status == "timeout":
            timeout_count += 1
            failures.append(
                {
                    "probe_category": r.request.category,
                    "legacy_table": r.request.legacy_table,
                    "legacy_column": r.request.legacy_column,
                    "status": "timeout",
                    "reason": r.reason or "timeout",
                }
            )
        elif r.status == "error":
            error_count += 1
            failures.append(
                {
                    "probe_category": r.request.category,
                    "legacy_table": r.request.legacy_table,
                    "legacy_column": r.request.legacy_column,
                    "status": "error",
                    "reason": r.reason or "unknown error",
                }
            )
        for f in r.findings:
            findings.append(_finding_to_dict(f))
            if f.severity == "blocker":
                blocker_count += 1
            elif f.severity == "warn":
                warn_count += 1
            else:
                info_count += 1

    requires_review = blocker_count > 0 or any(f.requires_human_decision for r in results for f in r.findings)

    return {
        "schema_version": "omnix-dm/edge-case-manifest/v1",
        "migration_id": migration_id,
        "timestamp": _now_iso(),
        "predecessor_hash": predecessor_hash,
        "findings": findings,
        "probe_failures": failures,
        "requires_operator_review": requires_review,
        "stats": {
            "total_probes_run": len(results),
            "total_findings": len(findings),
            "blocker_count": blocker_count,
            "warn_count": warn_count,
            "info_count": info_count,
            "timeout_count": timeout_count,
            "error_count": error_count,
        },
        "signing_algorithm": "ML-DSA-65",
        "public_key_fingerprint": ml_dsa_65.fingerprint(public_key),
    }


def emit(
    results: Tuple[ProbeResult, ...],
    migration_id: str,
    predecessor_hash: str,
    secret_key: bytes,
    public_key: bytes,
    output_root: Path,
) -> Path:
    if not predecessor_hash:
        raise ValueError(
            "D2 manifest_emitter requires a non-empty predecessor_hash "
            "(must chain to D1 column-mapping receipt)"
        )
    manifest = build_manifest(results, migration_id, predecessor_hash, public_key)
    Draft202012Validator(EDGE_CASE_MANIFEST_SCHEMA).validate(manifest)
    canonical, sig_hex = sign_canonical(manifest, secret_key)

    out_dir = Path(output_root) / migration_id
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "edge-case-manifest.json"
    sig_path = out_dir / "edge-case-manifest.json.sig"
    chain_path = out_dir / "edge-case-manifest.chainhash"

    _atomic_write(json_path, canonical)
    _atomic_write(sig_path, sig_hex.encode("ascii"))
    chain_hash = merkle_chain.next_hash(predecessor_hash, canonical)
    _atomic_write(chain_path, chain_hash.encode("ascii"))
    return json_path


__all__ = ["build_manifest", "emit"]
