"""RebuildAttempt — single-call record of one LLM dispatch.

Hashes are sha256 hex digests. Stored so receipts can prove the spec + prompt
that produced a given response without retaining the full text.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def sha256_hex(s: str) -> str:
    """Deterministic sha256 of a UTF-8 string."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RebuildAttempt:
    """One LLM dispatch + capture."""

    node_fqn: str
    spec_hash: str
    prompt_template_version: str
    prompt_text_hash: str
    response_text: str
    timestamp: datetime
    model: str
    attempt_number: int = 1  # 1-indexed; >1 only set by Phase 7 retry wrapper

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RebuildAttempt:
        d = dict(d)
        if isinstance(d["timestamp"], str):
            d["timestamp"] = datetime.fromisoformat(d["timestamp"])
        return cls(**d)

    @classmethod
    def now_utc(cls) -> datetime:
        """Single canonical clock source — overridable in tests via monkeypatch."""
        return datetime.now(timezone.utc)
