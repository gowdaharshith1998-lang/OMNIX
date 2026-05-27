"""OMNIX-DM D4 — Exhaustive Bulk Import (PR C).

Consumes PR B's signed ``TransformerSpec`` receipts; streams every row from
legacy through the per-column transformers in a fenced subprocess pool;
batch-writes to target via PG ``COPY FROM STDIN`` or parameterized INSERTs;
captures every failure into a signed quarantine manifest; emits one
ML-DSA-65 signed ``BatchReceipt`` per (table, batch_no); persists a
``checkpoint.json`` so the operator can resume after any crash.

Idempotency: ``batch_id = sha256(migration_id || table || batch_no)`` plus
the operator-supplied ``__omnix_batch_id`` column on every target table
means rerunning the same ``migration_id`` is a no-op.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
