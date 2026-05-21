"""Build and write supplementary provenance sidecars."""

from __future__ import annotations

import json
from collections.abc import Iterable
from hashlib import sha256
from pathlib import Path
from typing import Any

from omnix.provenance.fingerprint import canonical_subgraph_fingerprint
from omnix.provenance.signer import SidecarSigner, canonical_sidecar_bytes

SCHEMA_VERSION = "omnix.provenance.v1"


def build_sidecar(
    target_program_id: str,
    retrieval_bundle: Any,
    traversal_result: Any,
    skills_applied: Iterable[Any],
    enrichment_data_hash: str,
    token_cost: dict[str, int | float],
) -> dict[str, Any]:
    node_ids = list(getattr(retrieval_bundle, "node_ids", []) or [])
    traversal_path = list(getattr(traversal_result, "traversal_path", []) or [])
    edge_ids = [
        str(event.get("edge_id"))
        for event in traversal_path
        if isinstance(event, dict) and event.get("edge_id") is not None
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "target_program_id": target_program_id,
        "subgraph_fingerprint": canonical_subgraph_fingerprint(node_ids, edge_ids),
        "retrieval_modes": dict(getattr(retrieval_bundle, "retrieval_modes", {}) or {}),
        "traversal_path": traversal_path,
        "skills_applied": [_skill_tuple(skill) for skill in skills_applied],
        "enrichment_data_hash": enrichment_data_hash,
        "token_cost": dict(token_cost),
    }


def build_minimal_sidecar(
    *,
    program_id: str,
    receipt_path: Path,
    receipt_sig_path: Path | None = None,
    retrieval_modes: dict[str, int] | None = None,
    traversal_path: list[dict[str, Any]] | None = None,
    skills_applied: list[Any] | None = None,
    token_cost: dict[str, int | float] | None = None,
) -> dict[str, Any]:
    receipt_bytes = receipt_path.read_bytes()
    sig_bytes = receipt_sig_path.read_bytes() if receipt_sig_path and receipt_sig_path.is_file() else b""
    enrichment_hash = sha256(receipt_bytes + sig_bytes).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "target_program_id": program_id,
        "receipt_sha256": sha256(receipt_bytes).hexdigest(),
        "receipt_signature_sha256": sha256(sig_bytes).hexdigest() if sig_bytes else None,
        "subgraph_fingerprint": canonical_subgraph_fingerprint([program_id], []),
        "retrieval_modes": dict(retrieval_modes or {}),
        "traversal_path": list(traversal_path or []),
        "skills_applied": [_skill_tuple(skill) for skill in (skills_applied or [])],
        "enrichment_data_hash": enrichment_hash,
        "token_cost": dict(token_cost or {}),
    }


def write_sidecar(
    run_dir: Path,
    program_id: str,
    sidecar_dict: dict[str, Any],
    signer: SidecarSigner,
) -> tuple[Path, Path]:
    run_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = run_dir / f"{program_id}.provenance.json"
    sig_path = run_dir / f"{program_id}.provenance.sig"
    sidecar_path.write_bytes(canonical_sidecar_bytes(sidecar_dict))
    sig_path.write_text(signer.sign_b64(sidecar_dict) + "\n", encoding="utf-8")
    return sidecar_path, sig_path


def load_sidecar(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _skill_tuple(skill: Any) -> dict[str, Any]:
    if isinstance(skill, dict):
        return {
            "skill_id": str(skill.get("skill_id") or skill.get("id") or ""),
            "version": int(skill.get("version", 1)),
            "t_valid_at_use": str(skill.get("t_valid") or skill.get("t_valid_at_use") or ""),
        }
    return {
        "skill_id": str(getattr(skill, "skill_id", getattr(skill, "id", ""))),
        "version": int(getattr(skill, "version", 1)),
        "t_valid_at_use": str(getattr(skill, "t_valid", "")),
    }
