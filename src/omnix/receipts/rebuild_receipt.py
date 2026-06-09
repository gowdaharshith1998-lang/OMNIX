# Compliance: P17 (no mutable default args in receipt modules).
"""Per-node rebuild receipt schema for the M1 finisher Phase 6 pipeline.

Schema v1.0. Adding fields is allowed via additive evolution (bump minor).
Removing/renaming fields is breaking (bump major).

Honesty gate (the load-bearing invariant): gates 5 (property-based testing)
and 6 (behavioral equivalence) are NOT implemented in M1. Receipts emitted
in M1 MUST mark these two gates as `deferred_m2`, never `passed` and never
`failed`. Conflating "no verification ran" with "verification passed" would
defeat the receipt's epistemic value and break OMNIX's positioning.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature

from omnix.receipts.finding_keys import (
    _load_private_key,
    _load_public_key,
    project_privkey_path,
)

SCHEMA_VERSION = "1.0"

# Gate-status vocabulary. M1 receipts may use any of these; M2 will drop
# "deferred_m2" from the allowed set once gates 5+6 actually run.
VALID_GATE_STATUSES = frozenset({"passed", "failed", "deferred_m2", "skipped"})

# Gates 5 and 6 are unimplemented in M1. Receipts emitted in M1 must mark
# them as deferred_m2. This is the honesty invariant.
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


@dataclass(frozen=True)
class GateResult:
    """One verification gate's result on a single rebuild attempt."""

    gate_number: int
    gate_name: str
    status: str
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
            raise ValueError(
                f"status must be one of {sorted(VALID_GATE_STATUSES)}, "
                f"got {self.status!r}"
            )
        # HONESTY INVARIANT: gates 5+6 in M1 receipts must be deferred_m2.
        # If a future M2 receipt emitter starts populating real results, it
        # must remove these gates from M2_DEFERRED_GATES at the same commit.
        if self.gate_number in M2_DEFERRED_GATES and self.status != "deferred_m2":
            raise ValueError(
                f"gate {self.gate_number} ({self.gate_name}) is M2-deferred "
                f"and MUST have status='deferred_m2' in M1 receipts, "
                f"got {self.status!r}. Marking it 'passed' would conflate "
                f"unverified with verified — that's the honesty gate."
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
        # Re-enforce honesty invariant at the receipt level — defensive even
        # though GateResult.__post_init__ also enforces it.
        for g in self.gate_results:
            if g.gate_number in M2_DEFERRED_GATES and g.status != "deferred_m2":
                raise ValueError(
                    f"gate {g.gate_number} ({g.gate_name}) MUST be deferred_m2 "
                    f"in M1 receipts (honesty gate)"
                )

    def canonical_json(self) -> bytes:
        """Deterministic byte representation for signing.

        Gate results are emitted in gate_number order so two receipts built
        from the same logical inputs sign-equal.
        """
        payload: dict[str, Any] = asdict(self)
        payload["gate_results"] = sorted(
            payload["gate_results"], key=lambda g: int(g["gate_number"])
        )
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RebuildReceipt:
        gates = tuple(
            GateResult(
                gate_number=int(g["gate_number"]),
                gate_name=str(g["gate_name"]),
                status=str(g["status"]),
                details=dict(g.get("details") or {}),
            )
            for g in d.get("gate_results") or []
        )
        return cls(
            schema_version=str(d.get("schema_version", SCHEMA_VERSION)),
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


def default_m2_deferred_gate_results() -> tuple[GateResult, ...]:
    """Return GateResult tuples for gates 5+6 in their canonical M1 state."""
    return tuple(
        GateResult(
            gate_number=n,
            gate_name=GATE_NAMES[n],
            status="deferred_m2",
            details={
                "reason": (
                    f"Gate {n} ({GATE_NAMES[n]}) is M2 scope — not implemented "
                    "in M1 finisher. Status is `deferred_m2`, NOT `passed`. "
                    "See docs/M1_DEMO.md for what this receipt does and does "
                    "not prove."
                )
            },
        )
        for n in sorted(M2_DEFERRED_GATES)
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
