"""Drata evidence-push integration.

Each ML-DSA-65 signed receipt automatically becomes a Drata evidence artifact
through this module. The actual upload uses Drata's REST API at
``https://app.drata.com/api/v1``; we keep the SDK surface narrow so tests can
substitute a fake transport.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class DrataEvidence:
    control_id: str
    title: str
    summary: str
    payload_b64: str
    payload_sha256: str
    metadata: dict = field(default_factory=dict)


class DrataTransport(Protocol):
    def push(self, evidence: DrataEvidence) -> str: ...


class FakeDrataTransport:
    def __init__(self) -> None:
        self.uploaded: list[DrataEvidence] = []

    def push(self, evidence: DrataEvidence) -> str:
        self.uploaded.append(evidence)
        return f"drata-{len(self.uploaded)}"


# Mapping from OMNIX receipt kind to Drata control id. Each receipt is
# evidence for one or more SOC 2 controls.
_CONTROL_MAP: dict[str, list[str]] = {
    "replication.behavioral": ["CC7.2", "CC8.1"],   # System monitoring + change mgmt
    "cutover.authorization":  ["CC7.2", "CC8.1"],
    "cutover.rollback":       ["CC7.2", "CC8.1"],
    "rebuild.gate":           ["CC4.1"],
}


def receipt_to_evidence(*, receipt_kind: str, receipt_payload: bytes,
                        receipt_sha256: str, control_id: str,
                        metadata: dict | None = None) -> DrataEvidence:
    import base64
    return DrataEvidence(
        control_id=control_id,
        title=f"OMNIX receipt — {receipt_kind}",
        summary=(
            f"ML-DSA-65 (FIPS 204) signed receipt of kind {receipt_kind!r}. "
            "Provides cryptographic, post-quantum attestation."
        ),
        payload_b64=base64.b64encode(receipt_payload).decode(),
        payload_sha256=receipt_sha256,
        metadata=metadata or {},
    )


def push_evidence_for_receipts(
    transport: DrataTransport,
    receipts: Iterable[Mapping],
) -> list[str]:
    """Iterate signed receipts and push each one to Drata as evidence.

    Receipts must be dicts with keys: receipt_kind, payload (bytes),
    payload_sha256, metadata.
    """
    out: list[str] = []
    for r in receipts:
        controls = _CONTROL_MAP.get(r["receipt_kind"], [])
        for control_id in controls:
            evidence = receipt_to_evidence(
                receipt_kind=r["receipt_kind"],
                receipt_payload=r["payload"],
                receipt_sha256=r["payload_sha256"],
                control_id=control_id,
                metadata=r.get("metadata"),
            )
            out.append(transport.push(evidence))
    return out


def list_supported_controls() -> dict[str, list[str]]:
    """Surface the receipt-kind -> control-id mapping (for docs + dashboards)."""
    return {k: list(v) for k, v in _CONTROL_MAP.items()}
