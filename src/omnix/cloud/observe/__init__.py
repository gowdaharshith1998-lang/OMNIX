"""Phase B2 — Live observation collectors.

Three sources feed the M2 GraphRAG as behavioral observations:
  * Cilium Tetragon (eBPF) — HTTP/SQL/DNS/exec/file syscalls at kernel layer
  * Debezium — log-based CDC for PostgreSQL/MySQL/SQL Server/Oracle
  * Mainframe bridges — tcVISION / Ironstream / C\\Prof for z/OS

All collectors share a common Observation envelope so the spec-mining stage
treats them uniformly.
"""

from __future__ import annotations

from omnix.cloud.observe.envelope import (  # noqa: F401
    Observation,
    ObservationKind,
    ObservationSink,
    InMemorySink,
)
