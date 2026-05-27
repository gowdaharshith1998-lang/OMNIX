"""OMNIX-DM D5 — Change Data Capture (PR C).

Strangler-Fig data plane: after D4 bulk completes from snapshot LSN ``L0``,
D5 captures every legacy write from ``L0`` onwards via PostgreSQL logical
replication (``pgoutput`` plugin), replays each event through the same
``TransformerSpec`` from PR B against target, tracks lag, and emits a
signed ``CutoverProposal`` when statistical parity is sustained.

The Oracle (LogMiner) and MySQL (binlog) adapters are explicitly stubbed
with ``NotYetImplementedInPRC`` and deferred to PR D — Codex honesty.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
