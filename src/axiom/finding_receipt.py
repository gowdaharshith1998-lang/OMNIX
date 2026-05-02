# Compliance: P17 (no mutable default args in AXIOM modules).
"""Per-finding cryptographic receipt schema for slice 18d.

Schema is locked at v1.0. Adding fields is allowed via additive evolution
(bump schema_version minor). Removing or renaming fields is a breaking
change — bump major.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = "1.0"

VALID_SEVERITIES = frozenset({"info", "low", "med", "high", "critical"})

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_HEX16 = re.compile(r"^[0-9a-f]{16}$")
_ISO8601_Z = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
)


@dataclass(frozen=True)
class FindingReceipt:
    finding_id: str
    project_id: str
    file: str
    line_start: int
    line_end: int
    severity: str
    rule: str
    model: str
    prompt_hash: Optional[str]
    response_hash: Optional[str]
    finding_summary: str
    code_snippet_hash: str
    timestamp: str
    omnix_version: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not _HEX32.match(self.finding_id):
            raise ValueError(
                f"finding_id must be 32 lowercase hex chars, got {self.finding_id!r}"
            )
        if not _HEX16.match(self.project_id):
            raise ValueError(
                f"project_id must be 16 lowercase hex chars, got {self.project_id!r}"
            )
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(
                f"severity must be one of {sorted(VALID_SEVERITIES)}, "
                f"got {self.severity!r}"
            )
        if len(self.finding_summary) > 200:
            raise ValueError(
                f"finding_summary too long ({len(self.finding_summary)} > 200)"
            )
        if self.line_start < 1 or self.line_end < self.line_start:
            raise ValueError(f"invalid line range: {self.line_start}-{self.line_end}")
        if not self.file or self.file.startswith("/") or "\\" in self.file:
            raise ValueError(f"file must be a POSIX path relative to project root, got {self.file!r}")
        for name, h in (
            ("code_snippet_hash", self.code_snippet_hash),
            ("prompt_hash", self.prompt_hash),
            ("response_hash", self.response_hash),
        ):
            if h is None:
                continue
            if not _HEX64.match(h):
                raise ValueError(f"{name} must be 64 lowercase hex chars or null")
        if not _ISO8601_Z.match(self.timestamp):
            raise ValueError(
                f"timestamp must be ISO 8601 UTC with milliseconds and Z suffix, "
                f"got {self.timestamp!r}"
            )
        if not self.omnix_version:
            raise ValueError("omnix_version must be non-empty")

    def canonical_json(self) -> bytes:
        """Deterministic byte representation for signing."""
        return json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FindingReceipt:
        return cls(
            schema_version=str(d.get("schema_version", SCHEMA_VERSION)),
            finding_id=str(d["finding_id"]),
            project_id=str(d["project_id"]),
            file=str(d["file"]),
            line_start=int(d["line_start"]),
            line_end=int(d["line_end"]),
            severity=str(d["severity"]),
            rule=str(d["rule"]),
            model=str(d["model"]),
            prompt_hash=_optional_hash(d.get("prompt_hash")),
            response_hash=_optional_hash(d.get("response_hash")),
            finding_summary=str(d["finding_summary"]),
            code_snippet_hash=str(d["code_snippet_hash"]),
            timestamp=str(d["timestamp"]),
            omnix_version=str(d["omnix_version"]),
        )


def _optional_hash(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v)
    if s.lower() == "null":
        return None
    return s


def compute_finding_id(project_id: str, file: str, line_start: int, rule: str) -> str:
    """Deterministic finding_id from stable inputs."""
    payload = f"{project_id}|{file}|{line_start}|{rule}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


def compute_project_id(project_root: Path) -> str:
    """Deterministic project_id from canonical absolute path."""
    canonical = project_root.resolve(strict=False).as_posix()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def now_iso8601_utc() -> str:
    """ISO 8601 UTC with millisecond precision and trailing Z."""
    dt = datetime.now(timezone.utc)
    ms = dt.microsecond // 1000
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}Z"
