"""Structured progress event emission."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TextIO


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class JsonProgressEmitter:
    run_id: str
    stream: TextIO | None = None

    def emit(self, kind: str, payload: dict[str, object]) -> None:
        event = {"ts": utc_now_iso(), "run_id": self.run_id, "kind": kind, **payload}
        print(json.dumps(event, sort_keys=True), file=self.stream or sys.stderr)
