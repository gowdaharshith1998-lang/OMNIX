"""Oracle CDC adapter STUB — deferred to PR D.

PR D's plan (documented here for the next agent):

  * Use ``cx_Oracle``'s LogMiner support to read redo logs.
  * Track SCN per relation; ``start_scn`` is the analogue of PG's snapshot
    LSN. The handoff from D4 bulk to D5 CDC for Oracle is "capture SCN at
    consistent snapshot start, then ``DBMS_LOGMNR.START_LOGMNR`` from that
    SCN".
  * Alternative: an Oracle GoldenGate adapter for customers who already
    licence GoldenGate. The interface (``CDCAdapter.start``) would emit
    the same :class:`omnix.dm._types.ChangeEvent` shape.
  * Replica identity equivalent: ``SUPPLEMENTAL LOG DATA`` setting; D5
    rejects with a clear error if not set so the operator can fix.

PR C ships this stub so the adapter registry is honest — any customer
attempting Oracle D5 today gets a clear ``NotYetImplementedInPRC`` with
PR D referenced, never a silent NOP.
"""

from __future__ import annotations

from typing import Any, Iterable

from omnix.dm.d5_change_data_capture.cdc_core import (
    NotYetImplementedInPRC,
    register_adapter,
)


class OracleAdapter:
    """Stub. ``start()`` raises ``NotYetImplementedInPRC`` with a message
    pointing to PR D as the implementer."""

    def __init__(self, dsn: Any):
        self.dsn = dsn

    def start(self, slot_name: str, publication_name: str) -> Iterable:
        raise NotYetImplementedInPRC(
            "Oracle LogMiner adapter is PR D scope — see "
            "src/omnix/dm/d5_change_data_capture/oracle_adapter.py for the plan"
        )


register_adapter("oracle", OracleAdapter)


__all__ = ["OracleAdapter"]
