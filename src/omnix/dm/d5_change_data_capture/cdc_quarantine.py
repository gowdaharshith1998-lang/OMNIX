"""CDC event quarantine — same signed-manifest shape as D4's quarantine."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from jsonschema import Draft202012Validator

from omnix.crypto import ml_dsa_65
from omnix.dm._types import CDCEventQuarantineEntry
from omnix.dm.receipts.ml_dsa_65_signer import sign_canonical
from omnix.dm.receipts.schemas import QUARANTINE_MANIFEST_SCHEMA


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


def _entry_to_dict(e: CDCEventQuarantineEntry) -> dict:
    return {
        "migration_id": e.migration_id,
        "event_lsn": e.event_lsn,
        "relation_id": e.relation_id,
        "table": e.table,
        "op": e.op,
        "failure_category": e.failure_category,
        "failure_detail": e.failure_detail,
        "timestamp": e.timestamp,
    }


class CDCQuarantineLog:
    """Accumulate :class:`CDCEventQuarantineEntry` and flush a signed manifest."""

    def __init__(
        self,
        *,
        migration_id: str,
        output_root: Path,
        secret_key: bytes,
        public_key: bytes,
    ):
        self.migration_id = migration_id
        self.output_root = Path(output_root)
        self.secret_key = secret_key
        self.public_key = public_key
        self._entries: List[CDCEventQuarantineEntry] = []

    def record(self, entry: CDCEventQuarantineEntry) -> None:
        self._entries.append(entry)

    def __len__(self) -> int:
        return len(self._entries)

    def flush(self) -> Optional[Path]:
        if not self._entries:
            return None
        payload = {
            "schema_version": "omnix-dm/quarantine-manifest/v1",
            "migration_id": self.migration_id,
            "phase": "d5_cdc",
            "entries": [_entry_to_dict(e) for e in self._entries],
            "signing_algorithm": "ML-DSA-65",
            "public_key_fingerprint": ml_dsa_65.fingerprint(self.public_key),
        }
        Draft202012Validator(QUARANTINE_MANIFEST_SCHEMA).validate(payload)
        canonical, sig_hex = sign_canonical(payload, self.secret_key)
        out_dir = self.output_root / self.migration_id / "d5"
        json_path = out_dir / "cdc-quarantine-manifest.json"
        sig_path = out_dir / "cdc-quarantine-manifest.json.sig"
        _atomic_write_secure(json_path, canonical)
        _atomic_write_secure(sig_path, sig_hex.encode("ascii"))
        return json_path


__all__ = ["CDCQuarantineLog"]
