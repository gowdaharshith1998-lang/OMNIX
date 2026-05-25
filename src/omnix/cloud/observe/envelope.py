"""Behavioral observation envelope shared by all live-collector backends."""

from __future__ import annotations

import enum
import re
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol


class ObservationKind(str, enum.Enum):
    HTTP_REQUEST = "http_request"
    SQL_QUERY = "sql_query"
    DNS_LOOKUP = "dns_lookup"
    SYSCALL_EXEC = "syscall_exec"
    FILE_OPEN = "file_open"
    CDC_INSERT = "cdc_insert"
    CDC_UPDATE = "cdc_update"
    CDC_DELETE = "cdc_delete"
    MAINFRAME_JCL_JOB = "mainframe_jcl_job"
    MAINFRAME_CICS_TXN = "mainframe_cics_txn"
    MAINFRAME_VSAM_OP = "mainframe_vsam_op"


@dataclass
class Observation:
    kind: ObservationKind
    pod: str | None
    node: str | None
    service: str | None
    payload: dict[str, Any] = field(default_factory=dict)
    captured_at: float = field(default_factory=time.time)
    redacted_fields: tuple[str, ...] = ()


# Common PII redaction patterns.
_PII_PATTERNS = [
    (re.compile(r"\b[\w.\-]+@[\w.\-]+\.\w+\b"), "<email>"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "<ssn>"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "<pan>"),
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "<ipv4>"),
]


def redact(payload: Any) -> tuple[Any, list[str]]:
    """Walk the payload and replace PII matches. Returns (redacted, fields)."""
    fields: list[str] = []

    def _walk(node: Any, path: str = "") -> Any:
        if isinstance(node, str):
            new = node
            for pattern, replacement in _PII_PATTERNS:
                if pattern.search(new):
                    new = pattern.sub(replacement, new)
                    fields.append(path or "$")
            return new
        if isinstance(node, dict):
            return {k: _walk(v, f"{path}.{k}" if path else k) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(v, f"{path}[{i}]") for i, v in enumerate(node)]
        return node

    return _walk(payload), fields


class ObservationSink(Protocol):
    def absorb(self, obs: Observation) -> None: ...

    def drain(self) -> list[Observation]: ...


class InMemorySink:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buf: list[Observation] = []

    def absorb(self, obs: Observation) -> None:
        with self._lock:
            self._buf.append(obs)

    def drain(self) -> list[Observation]:
        with self._lock:
            out = self._buf
            self._buf = []
            return out


def absorb_many(sink: ObservationSink, observations: Iterable[Observation]) -> None:
    for obs in observations:
        sink.absorb(obs)
