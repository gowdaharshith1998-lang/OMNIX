"""Resume cursor — operator-mutable, NOT signed.

The checkpoint persists ``(table, last_batch_no_complete, last_pk_seen)`` so
that an SIGINT'd or crashed bulk run resumes from the next batch on rerun.
We deliberately do NOT sign this file — operator intervention (clearing a
table partition manually, for instance) needs to be able to edit it. The
BatchReceipts upstream provide the cryptographic audit trail; the checkpoint
is just a fast resume hint.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass(frozen=True)
class TableCheckpoint:
    table: str
    last_batch_no_complete: int
    last_pk_seen: Optional[str]


@dataclass(frozen=True)
class CheckpointState:
    migration_id: str
    tables: Dict[str, TableCheckpoint]


def _atomic_write(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)


def read_checkpoint(path: Path) -> Optional[CheckpointState]:
    p = Path(path)
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    tables = {
        k: TableCheckpoint(
            table=v["table"],
            last_batch_no_complete=v["last_batch_no_complete"],
            last_pk_seen=v.get("last_pk_seen"),
        )
        for k, v in data.get("tables", {}).items()
    }
    return CheckpointState(migration_id=data["migration_id"], tables=tables)


def write_checkpoint(path: Path, state: CheckpointState) -> None:
    payload = {
        "migration_id": state.migration_id,
        "tables": {k: asdict(v) for k, v in state.tables.items()},
    }
    _atomic_write(Path(path), json.dumps(payload, sort_keys=True).encode("utf-8"))


__all__ = [
    "TableCheckpoint",
    "CheckpointState",
    "read_checkpoint",
    "write_checkpoint",
]
