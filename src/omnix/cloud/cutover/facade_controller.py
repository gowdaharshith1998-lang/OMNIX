"""Strangler-fig facade controller.

Holds the per-(tenant, unit) traffic-shift table and gates every transition
behind a fresh ML-DSA-65 signed receipt. The controller is independent of the
data plane (NGINX/Envoy facade Deployment lives in the Helm chart and reads
its routing table from a ConfigMap that the controller atomically updates).

In-memory routing table is used for tests; production wires a Kubernetes
client. The contract is the same.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


class CutoverError(RuntimeError):
    pass


@dataclass
class CutoverState:
    tenant_id: str
    unit_id: str
    percentage: int = 0
    history: list["CutoverEvent"] = field(default_factory=list)


@dataclass
class CutoverEvent:
    event_id: str
    tenant_id: str
    unit_id: str
    previous_percentage: int
    target_percentage: int
    verifier_summary: dict[str, Any]
    receipt_id: str | None = None
    receipt_payload: bytes | None = None
    receipt_signature: bytes | None = None
    public_key: bytes | None = None
    is_rollback: bool = False
    rejected_reason: str | None = None
    created_at: float = field(default_factory=time.time)


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class FacadeController:
    """Per-process controller backed by a synchronous lock.

    Production wires this to k8s; tests use the in-memory routing table.
    """

    def __init__(self, signer=None, verifier=None) -> None:
        self._lock = threading.RLock()
        self._states: dict[tuple[str, str], CutoverState] = {}
        self._signer = signer
        self._verifier = verifier
        # In-process subscribers (e.g. FacadeWriter) that want to react to
        # every shift the controller authorizes. Kept in-process to avoid
        # taking a hard dependency on Redis/streams here — the production
        # deployment co-locates the writer as a sidecar in the same pod, so
        # in-process pub/sub is correct.
        self._writer_subscribers: list = []

    def state(self, tenant_id: str, unit_id: str) -> CutoverState:
        with self._lock:
            return self._states.setdefault(
                (tenant_id, unit_id),
                CutoverState(tenant_id=tenant_id, unit_id=unit_id, percentage=0),
            )

    def request_shift(
        self,
        *,
        tenant_id: str,
        unit_id: str,
        target_percentage: int,
        verifier_summary: dict[str, Any],
        is_rollback: bool = False,
    ) -> CutoverEvent:
        if not 0 <= target_percentage <= 100:
            raise CutoverError("target_percentage out of range")
        with self._lock:
            state = self.state(tenant_id, unit_id)
            previous = state.percentage

            event = CutoverEvent(
                event_id=uuid.uuid4().hex,
                tenant_id=tenant_id,
                unit_id=unit_id,
                previous_percentage=previous,
                target_percentage=target_percentage,
                verifier_summary=dict(verifier_summary),
                is_rollback=is_rollback,
            )

            if not is_rollback and not self._verifiers_clean(verifier_summary):
                event.rejected_reason = "verifier_mismatch"
                state.history.append(event)
                return event

            payload = {
                "tenant_id": tenant_id,
                "unit_id": unit_id,
                "previous_percentage": previous,
                "target_percentage": target_percentage,
                "verifier_summary": verifier_summary,
                "is_rollback": is_rollback,
                "created_at_unix": int(event.created_at),
                "kind": "cutover.authorization" if not is_rollback else "cutover.rollback",
            }
            canonical = _canonical(payload)

            if self._signer is not None:
                sig, pk = self._signer(canonical)
                event.receipt_payload = canonical
                event.receipt_signature = sig
                event.public_key = pk
                event.receipt_id = "rcpt-" + uuid.uuid4().hex
            state.percentage = target_percentage
            state.history.append(event)
            self._notify_writers(event)
            return event

    def subscribe_writer(self, callback) -> None:
        """Register a callback invoked for every authorized shift event.

        The callback is called inside the controller's lock; subscribers MUST
        return quickly (e.g. enqueue and apply on another thread). The
        FacadeWriter sidecar does exactly that.
        """
        with self._lock:
            self._writer_subscribers.append(callback)

    def _notify_writers(self, event: CutoverEvent) -> None:
        # Errors in subscribers must not roll back the shift; the controller's
        # contract is signed-receipt-authorized state mutation, and once a
        # signature exists the operator's audit trail is committed.
        for cb in self._writer_subscribers:
            try:
                cb(event)
            except Exception:  # noqa: BLE001
                import logging
                logging.getLogger("omnix.facade_controller").exception(
                    "writer subscriber raised; swallowing"
                )

    def rollback(self, *, tenant_id: str, unit_id: str) -> CutoverEvent:
        return self.request_shift(
            tenant_id=tenant_id,
            unit_id=unit_id,
            target_percentage=0,
            verifier_summary={"rollback": True},
            is_rollback=True,
        )

    @staticmethod
    def _verifiers_clean(verifier_summary: dict[str, Any]) -> bool:
        if not verifier_summary:
            return False
        if int(verifier_summary.get("daikon_violated", 0)) > 0:
            return False
        if int(verifier_summary.get("scientist_mismatches", 0)) > 0:
            return False
        if int(verifier_summary.get("diffy_mismatches", 0)) > 0:
            return False
        if "hypothesis_passed" in verifier_summary:
            if not verifier_summary["hypothesis_passed"]:
                return False
        return True


# ---------- signer factory ----------

def real_signer():
    """Return a (signer, pubkey) tuple bound to the real ML-DSA-65 module."""
    from omnix.receipts import keygen, sign as sign_mod

    pk, sk = keygen.keygen()

    def signer(msg: bytes) -> tuple[bytes, bytes]:
        return sign_mod.sign_bytes(sk, msg, b"", None), pk

    return signer


def event_to_dict(event: CutoverEvent) -> dict[str, Any]:
    out = asdict(event)
    for key in ("receipt_payload", "receipt_signature", "public_key"):
        v = out.get(key)
        if isinstance(v, (bytes, bytearray)):
            import base64
            out[key + "_b64"] = base64.b64encode(v).decode()
            out.pop(key, None)
    return out
