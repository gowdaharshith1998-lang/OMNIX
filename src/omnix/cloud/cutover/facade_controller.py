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
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
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

    def __init__(self, signer=None, verifier=None, event_bus=None) -> None:
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
        # Optional cross-pod broadcast (Redis Streams or in-memory). When set,
        # every authorized shift is published for the SSE endpoint to fan out
        # to facade_writer_runner sidecars on other pods. None preserves the
        # pre-existing single-process behavior used by most tests.
        self._event_bus = event_bus

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
        bus_payload: dict[str, Any] | None = None
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
            # Notify in-process subscribers (sync, fast) under lock to keep
            # ordering. Capture the bus payload here but publish after
            # releasing the lock — a Redis stall must not block every
            # other tenant/unit's controller mutation.
            self._notify_in_process_writers(event)
            if self._event_bus is not None and event.rejected_reason is None:
                bus_payload = _event_to_bus_payload(event)
            bus_event_id = event.event_id
        # Lock released — safe to do network I/O.
        if bus_payload is not None and self._event_bus is not None:
            try:
                self._event_bus.publish(bus_event_id, bus_payload)
            except Exception:  # noqa: BLE001
                import logging
                logging.getLogger("omnix.facade_controller").exception(
                    "event_bus.publish raised; swallowing (event already in audit history)"
                )
        return event

    def subscribe_writer(self, callback) -> None:
        """Register a callback invoked for every authorized shift event.

        The callback is called inside the controller's lock; subscribers MUST
        return quickly (e.g. enqueue and apply on another thread). The
        FacadeWriter sidecar does exactly that.
        """
        with self._lock:
            self._writer_subscribers.append(callback)

    def _notify_in_process_writers(self, event: CutoverEvent) -> None:
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

    def _notify_writers(self, event: CutoverEvent) -> None:
        """Backward-compat shim: the previous public API name.

        Kept so any external test or harness that exercised the private
        notify path still works. Internally request_shift now uses
        _notify_in_process_writers + a post-lock bus.publish to avoid
        holding the controller lock across network I/O.
        """
        self._notify_in_process_writers(event)
        if self._event_bus is not None and event.rejected_reason is None:
            try:
                self._event_bus.publish(event.event_id, _event_to_bus_payload(event))
            except Exception:  # noqa: BLE001
                import logging
                logging.getLogger("omnix.facade_controller").exception(
                    "event_bus.publish raised; swallowing"
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

_CUTOVER_KEY_LOCK = threading.Lock()
_CUTOVER_KEYPAIR: tuple[bytes, bytes] | None = None


def _cutover_key_dir() -> Path:
    raw = os.environ.get("OMNIX_CUTOVER_KEY_DIR")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".omnix" / "keys" / "cutover"


def _cutover_keypair() -> tuple[bytes, bytes]:
    """Load (or, on first use, create + persist) the long-lived cutover key.

    Persisted under OMNIX_CUTOVER_KEY_DIR (default ~/.omnix/keys/cutover/) as
    public.pem + secret.pem (secret mode 0600) and cached for the process.
    """
    global _CUTOVER_KEYPAIR
    with _CUTOVER_KEY_LOCK:
        if _CUTOVER_KEYPAIR is not None:
            return _CUTOVER_KEYPAIR
        from omnix.receipts import keystore
        from omnix.receipts.secure_keyfile import read_secret

        d = _cutover_key_dir()
        pub_p = d / "public.pem"
        sec_p = d / "secret.pem"
        if not (pub_p.is_file() and sec_p.is_file()):
            keystore.write_keypair_dir(d)
        pk = keystore.public_from_pem(pub_p.read_text(encoding="ascii"))
        sk = keystore.secret_from_pem(read_secret(sec_p))  # decrypts at rest when enabled
        _CUTOVER_KEYPAIR = (pk, sk)
        return _CUTOVER_KEYPAIR


def real_signer():
    """Return a signer bound to the PERSISTENT ML-DSA-65 cutover key.

    Previously this generated a *fresh ephemeral* keypair on every call, so a
    cutover authorization receipt could never be verified against a stable
    trust anchor — it proved nothing across processes or restarts. Now it
    loads a long-lived keypair (creating + persisting it once on first use),
    so receipts from any worker/pod verify against the same published key.
    """
    from omnix.receipts import sign as sign_mod

    pk, sk = _cutover_keypair()

    def signer(msg: bytes) -> tuple[bytes, bytes]:
        return sign_mod.sign_bytes(sk, msg, b"", None), pk

    return signer


def _event_to_bus_payload(event: CutoverEvent) -> dict[str, Any]:
    """Compact JSON-safe payload for the cross-pod event bus.

    Only fields the data plane needs are included — signatures stay on the
    audit side. Bytes are base64-encoded so the payload is plain JSON.
    """
    payload: dict[str, Any] = {
        "event_id": event.event_id,
        "tenant_id": event.tenant_id,
        "unit_id": event.unit_id,
        "previous_percentage": event.previous_percentage,
        "target_percentage": event.target_percentage,
        "verifier_summary": dict(event.verifier_summary),
        "is_rollback": event.is_rollback,
        "created_at": event.created_at,
    }
    if event.receipt_id is not None:
        payload["receipt_id"] = event.receipt_id
    return payload


def event_to_dict(event: CutoverEvent) -> dict[str, Any]:
    out = asdict(event)
    for key in ("receipt_payload", "receipt_signature", "public_key"):
        v = out.get(key)
        if isinstance(v, (bytes, bytearray)):
            import base64
            out[key + "_b64"] = base64.b64encode(v).decode()
            out.pop(key, None)
    return out
