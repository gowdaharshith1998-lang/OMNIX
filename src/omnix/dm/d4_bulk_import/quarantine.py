"""Quarantine log — append-only, signed, mode-0600 manifest.

PR C ships the file-mode floor; PR D will add per-tenant key wrapping.
Raw row values are omitted by default; ``OMNIX_DM_QUARANTINE_INCLUDE_VALUES=1``
re-enables them for pilots that explicitly opt in.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from jsonschema import Draft202012Validator

from omnix.crypto import ml_dsa_65
from omnix.dm._types import RowQuarantineEntry
from omnix.dm.receipts.ml_dsa_65_signer import sign_canonical
from omnix.dm.receipts.schemas import QUARANTINE_MANIFEST_SCHEMA


def _entry_to_dict(e: RowQuarantineEntry, include_values: bool) -> dict:
    out = {
        "migration_id": e.migration_id,
        "batch_id": e.batch_id,
        "row_offset": e.row_offset,
        "legacy_table": e.legacy_table,
        "legacy_pk_value_hash": e.legacy_pk_value_hash,
        "failure_category": e.failure_category,
        "failure_detail": e.failure_detail,
        "transformer_spec_hash": e.transformer_spec_hash,
        "retry_count": e.retry_count,
        "timestamp": e.timestamp,
    }
    if include_values and e.raw_values_json is not None:
        out["raw_values_json"] = e.raw_values_json
    return out


def _atomic_write_secure(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, target)
    os.chmod(target, 0o600)


class QuarantineLog:
    """Accumulate :class:`RowQuarantineEntry` records and flush a signed
    manifest. Entries are appended in arrival order; the manifest is rewritten
    in full on each flush (this is cheap because PR C runs are bounded —
    PR D will switch to a streaming format if customer corpora demand it)."""

    def __init__(
        self,
        *,
        migration_id: str,
        output_root: Path,
        secret_key: bytes,
        public_key: bytes,
        phase: str = "d4_bulk",
    ):
        self.migration_id = migration_id
        self.output_root = Path(output_root)
        self.secret_key = secret_key
        self.public_key = public_key
        self.phase = phase
        self._entries: List[RowQuarantineEntry] = []
        self._include_values = bool(os.environ.get("OMNIX_DM_QUARANTINE_INCLUDE_VALUES"))

    def record(self, entry: RowQuarantineEntry) -> None:
        self._entries.append(entry)

    def extend(self, entries) -> None:
        self._entries.extend(entries)

    def __len__(self) -> int:
        return len(self._entries)

    def flush(self) -> Optional[Path]:
        if not self._entries:
            return None
        payload = {
            "schema_version": "omnix-dm/quarantine-manifest/v1",
            "migration_id": self.migration_id,
            "phase": self.phase,
            "entries": [
                _entry_to_dict(e, self._include_values) for e in self._entries
            ],
            "signing_algorithm": "ML-DSA-65",
            "public_key_fingerprint": ml_dsa_65.fingerprint(self.public_key),
        }
        Draft202012Validator(QUARANTINE_MANIFEST_SCHEMA).validate(payload)
        canonical, sig_hex = sign_canonical(payload, self.secret_key)
        sub = "d4" if self.phase == "d4_bulk" else "d5"
        target_dir = self.output_root / self.migration_id / sub
        json_path = target_dir / "quarantine-manifest.json"
        sig_path = target_dir / "quarantine-manifest.json.sig"
        _atomic_write_secure(json_path, canonical)
        _atomic_write_secure(sig_path, sig_hex.encode("ascii"))
        return json_path


__all__ = ["QuarantineLog"]
