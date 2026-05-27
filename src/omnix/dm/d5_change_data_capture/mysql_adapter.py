"""MySQL CDC adapter STUB — deferred to PR D.

PR D's plan:

  * Use the ``mysql-replication`` library (PyMySQL-based) which parses
    row-based binary logs into Python events.
  * Track GTID (Global Transaction ID) as the PG-LSN analogue. The handoff
    from D4 bulk to D5 CDC is "FLUSH TABLES WITH READ LOCK; SHOW MASTER
    STATUS; UNLOCK TABLES → capture (binlog_file, binlog_position) → bulk
    from snapshot → start binlog reader at the captured position".
  * REPLICA IDENTITY equivalent: ``binlog_row_image = FULL`` to recover the
    old row on UPDATE/DELETE.

PR C ships this stub so any MySQL customer attempting D5 today gets an
honest ``NotYetImplementedInPRC`` with PR D referenced.
"""

from __future__ import annotations

from typing import Any, Iterable

from omnix.dm.d5_change_data_capture.cdc_core import (
    NotYetImplementedInPRC,
    register_adapter,
)


class MySQLAdapter:
    """Stub. ``start()`` raises ``NotYetImplementedInPRC``."""

    def __init__(self, dsn: Any):
        self.dsn = dsn

    def start(self, slot_name: str, publication_name: str) -> Iterable:
        raise NotYetImplementedInPRC(
            "MySQL binlog adapter is PR D scope — see "
            "src/omnix/dm/d5_change_data_capture/mysql_adapter.py for the plan"
        )


register_adapter("mysql", MySQLAdapter)


__all__ = ["MySQLAdapter"]
