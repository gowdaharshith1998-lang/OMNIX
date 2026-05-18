# Compliance: P17 (no mutable default args in receipt modules).
"""Per-node rebuild receipt schema for the rebuild pipeline.

Schema v2.0 removes the M1-only ``deferred_m2`` gate status from new
emission. Legacy v1.0 receipts still load through a read-only migration:
``deferred_m2`` becomes ``skipped`` in the in-memory view, while signature
verification keeps using the original signed canonical bytes.

Honesty gate (the load-bearing invariant): no gate may use ``deferred_m2``
in v2, and a gate with ``status="passed"`` may not carry exception details.
Conflating "verification crashed" or "verification did not run" with
"verification passed" would defeat the receipt's epistemic value.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Sequence, cast

from cryptography.exceptions import InvalidSignature

from omnix.receipts.finding_keys import (
    _load_private_key,
    _load_public_key,
    project_privkey_path,
)

SCHEMA_VERSION = "2.0"

GateStatus = Literal[
    "passed",
    "failed",
    "runtime_crash",
    "skipped",
    "inconclusive",
    "deferred_m3",
]

VALID_GATE_STATUSES = frozenset(
    {
        "passed",
        "failed",
        "runtime_crash",
        "skipped",
        "inconclusive",
        "deferred_m3",
    }
)

# Gates 5 and 6 are wired after schema v2. Until then, new receipts mark
# them skipped with reason=gate_not_wired. Legacy v1 receipts may have used
# deferred_m2 for these gate numbers and are migrated on read.
M2_DEFERRED_GATES = frozenset({5, 6})

# Canonical gate names (1-6). M1 implements 1-4 mechanically; 5-6 are M2.
GATE_NAMES: dict[int, str] = {
    1: "syntactic",
    2: "typecheck",
    3: "signature",
    4: "dependency",
    5: "property_based",
    6: "behavioral_equivalence",
}

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX16 = re.compile(r"^[0-9a-f]{16}$")
_ISO8601_Z = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
)


class HonestyGateError(ValueError):
    """Raised when receipt evidence would overstate what ran or passed."""


@dataclass(frozen=True)
class GateResult:
    """One verification gate's result on a single rebuild attempt."""

    gate_number: int
    gate_name: str
    status: GateStatus
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.gate_number < 1 or self.gate_number > 6:
            raise ValueError(
                f"gate_number must be 1..6, got {self.gate_number}"
            )
        expected_name = GATE_NAMES[self.gate_number]
        if self.gate_name != expected_name:
            raise ValueError(
                f"gate_name for gate {self.gate_number} must be "
                f"{expected_name!r}, got {self.gate_name!r}"
            )
        if self.status not in VALID_GATE_STATUSES:
            if self.status == "deferred_m2":
                raise HonestyGateError(
                    "deferred_m2 is a legacy v1 read-only status and is not "
                    "valid in schema v2 receipts"
                )
            raise ValueError(
                f"status must be one of {sorted(VALID_GATE_STATUSES)}, "
                f"got {self.status!r}"
            )


@dataclass(frozen=True)
class RebuildReceipt:
    """Signed record of one rebuild attempt for one node."""

    project_id: str
    node_fqn: str
    target_language: str
    legacy_source_sha256: str
    rebuilt_source_sha256: str
    spec_hash: str
    prompt_template_version: str
    prompt_text_hash: str
    model: str
    gate_results: tuple[GateResult, ...]
    timestamp: str
    omnix_version: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not _HEX16.match(self.project_id):
            raise ValueError(
                f"project_id must be 16 lowercase hex chars, got {self.project_id!r}"
            )
        if not self.node_fqn:
            raise ValueError("node_fqn must be non-empty")
        if not self.target_language:
            raise ValueError("target_language must be non-empty")
        for name, h in (
            ("legacy_source_sha256", self.legacy_source_sha256),
            ("rebuilt_source_sha256", self.rebuilt_source_sha256),
            ("spec_hash", self.spec_hash),
            ("prompt_text_hash", self.prompt_text_hash),
        ):
            if not _HEX64.match(h):
                raise ValueError(f"{name} must be 64 lowercase hex chars")
        if not self.prompt_template_version:
            raise ValueError("prompt_template_version must be non-empty")
        if not self.model:
            raise ValueError("model must be non-empty")
        if not _ISO8601_Z.match(self.timestamp):
            raise ValueError(
                f"timestamp must be ISO 8601 UTC with milliseconds and Z, "
                f"got {self.timestamp!r}"
            )
        if not self.omnix_version:
            raise ValueError("omnix_version must be non-empty")
        # All six gates must appear in receipts, even if status=skipped.
        # Tests can spot-check by inspecting `gate_results` length + indices.
        nums = [g.gate_number for g in self.gate_results]
        if sorted(nums) != [1, 2, 3, 4, 5, 6]:
            raise ValueError(
                f"gate_results must contain exactly gates 1..6 in any order, "
                f"got {nums}"
            )
        if self.schema_version not in {"1.0", "2.0"}:
            raise ValueError(
                f"schema_version must be '1.0' or '2.0', got {self.schema_version!r}"
            )
        # Re-enforce honesty invariants at the receipt level — defensive even
        # if a caller bypassed GateResult.__post_init__.
        for g in self.gate_results:
            if g.status == "deferred_m2":
                raise HonestyGateError(
                    f"gate {g.gate_number} ({g.gate_name}) uses legacy "
                    "status 'deferred_m2'; v2 receipts must migrate it to "
                    "skipped or emit a real gate status"
                )
            if g.status == "passed" and "exception" in g.details:
                raise HonestyGateError(
                    f"gate {g.gate_number} ({g.gate_name}) is marked passed "
                    "but includes exception details"
                )

    def canonical_json(self) -> bytes:
        """Deterministic byte representation for signing.

        Gate results are emitted in gate_number order so two receipts built
        from the same logical inputs sign-equal. Legacy v1 receipts loaded
        via from_dict may carry original signed bytes so read migration does
        not invalidate existing Ed25519 signatures.
        """
        legacy_signed_bytes = getattr(self, "_signature_canonical_json", None)
        if legacy_signed_bytes is not None:
            return legacy_signed_bytes
        payload: dict[str, Any] = asdict(self)
        return _canonical_json_from_dict(payload)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RebuildReceipt:
        schema_version = str(d.get("schema_version", SCHEMA_VERSION))
        legacy_signed_bytes = (
            _canonical_json_from_dict(d) if schema_version == "1.0" else None
        )
        gates = tuple(_gate_from_dict(g, schema_version) for g in d.get("gate_results") or [])
        receipt = cls(
            schema_version=schema_version,
            project_id=str(d["project_id"]),
            node_fqn=str(d["node_fqn"]),
            target_language=str(d["target_language"]),
            legacy_source_sha256=str(d["legacy_source_sha256"]),
            rebuilt_source_sha256=str(d["rebuilt_source_sha256"]),
            spec_hash=str(d["spec_hash"]),
            prompt_template_version=str(d["prompt_template_version"]),
            prompt_text_hash=str(d["prompt_text_hash"]),
            model=str(d["model"]),
            gate_results=gates,
            timestamp=str(d["timestamp"]),
            omnix_version=str(d["omnix_version"]),
        )
        if legacy_signed_bytes is not None:
            object.__setattr__(receipt, "_signature_canonical_json", legacy_signed_bytes)
        return receipt

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["gate_results"] = sorted(
            d["gate_results"], key=lambda g: int(g["gate_number"])
        )
        return d


# ----- Helpers -------------------------------------------------------------


def sha256_hex_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_hex_text(text: str) -> str:
    return sha256_hex_bytes(text.encode("utf-8"))


def default_skipped_gate_results() -> tuple[GateResult, ...]:
    """Return not-yet-wired v2 results for gates 5+6."""
    return tuple(
        GateResult(
            gate_number=n,
            gate_name=GATE_NAMES[n],
            status="skipped",
            details={
                "reason": "gate_not_wired",
                "phase": "m2_phase1_schema_v2",
                "gate": GATE_NAMES[n],
            },
        )
        for n in sorted(M2_DEFERRED_GATES)
    )


def gates_summary(gate_results: Sequence[GateResult]) -> str:
    """Return the v2 CLI summary string for gate-result statuses."""
    counts = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "inconclusive": 0,
        "deferred_m3": 0,
    }
    for gate in gate_results:
        if gate.status == "runtime_crash":
            counts["failed"] += 1
        elif gate.status in counts:
            counts[gate.status] += 1
        else:  # Defensive for crafted objects that bypassed GateResult.
            counts["failed"] += 1
    return "/".join(f"{counts[s]}-{s}" for s in counts)


def _canonical_json_from_dict(d: dict[str, Any]) -> bytes:
    payload = dict(d)
    payload["gate_results"] = sorted(
        payload.get("gate_results") or [], key=lambda g: int(g["gate_number"])
    )
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _gate_from_dict(g: dict[str, Any], schema_version: str) -> GateResult:
    status = str(g["status"])
    details = dict(g.get("details") or {})
    if schema_version == "1.0" and status == "deferred_m2":
        status = "skipped"
        details = dict(details)
        details["migrated_from"] = "deferred_m2"
    return GateResult(
        gate_number=int(g["gate_number"]),
        gate_name=str(g["gate_name"]),
        status=cast(GateStatus, status),
        details=details,
    )


# ----- Sign / verify -------------------------------------------------------


def sign_rebuild(receipt: RebuildReceipt) -> str:
    """Sign a RebuildReceipt with the project's Ed25519 private key.

    Returns standard base64 (RFC 4648). The project key is the same
    keypair used by `sign_finding` — provisioned via `omnix axiom keygen`.

    Raises FileNotFoundError if no project key exists for `receipt.project_id`.
    """
    priv_path = project_privkey_path(receipt.project_id)
    if not priv_path.is_file():
        raise FileNotFoundError(
            f"no project key at {priv_path}; run `omnix axiom keygen` first."
        )
    priv = _load_private_key(priv_path)
    sig = priv.sign(receipt.canonical_json())
    return base64.b64encode(sig).decode("ascii")


def verify_rebuild(
    receipt: RebuildReceipt, signature_b64: str, pubkey_path: Path
) -> bool:
    """Verify a RebuildReceipt's detached signature against a project pubkey.

    Returns False on signature mismatch or malformed signature. Raises
    FileNotFoundError / InvalidFindingPublicKeyError if the pubkey itself
    is missing or malformed — those are operator-fix errors, not "verified
    false" errors.
    """
    pub = _load_public_key(pubkey_path)
    try:
        sig = base64.b64decode(signature_b64, validate=True)
    except Exception:
        return False
    try:
        pub.verify(sig, receipt.canonical_json())
        return True
    except InvalidSignature:
        return False
