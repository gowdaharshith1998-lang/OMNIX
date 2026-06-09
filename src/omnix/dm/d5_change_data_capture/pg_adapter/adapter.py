"""PG CDC adapter — wires the connection + parser + heartbeat into a
:class:`omnix.dm.d5_change_data_capture.cdc_core.CDCAdapter` implementation.

The adapter is mockable: pass any callable as ``message_source`` and the
adapter will iterate it as if it were a replication-connection message
stream. The default uses psycopg2's ``read_message`` API.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional

from omnix.dm._types import ChangeEvent
from omnix.dm.d5_change_data_capture.cdc_core import register_adapter
from omnix.dm.d5_change_data_capture.pg_adapter.pgoutput_parser import (
    ParseError,
    _State,
    parse_message,
)


class PGAdapter:
    """Live PG pgoutput adapter. Yields :class:`ChangeEvent` records."""

    def __init__(
        self,
        dsn: str,
        *,
        message_source: Optional[Callable[..., Iterable[bytes]]] = None,
    ):
        self.dsn = dsn
        self._message_source = message_source

    def start(
        self,
        slot_name: str,
        publication_name: str,
        *,
        start_lsn: str = "0/0",
    ) -> Iterable[ChangeEvent]:
        state = _State(relations={})
        if self._message_source is not None:
            iterator = self._message_source(
                dsn=self.dsn,
                slot_name=slot_name,
                publication_name=publication_name,
                start_lsn=start_lsn,
            )
        else:
            iterator = _live_iter(
                dsn=self.dsn,
                slot_name=slot_name,
                publication_name=publication_name,
                start_lsn=start_lsn,
            )
        for raw in iterator:
            try:
                event = parse_message(raw, state)
            except ParseError:
                # Bubble up — the replayer will catch and quarantine.
                raise
            if event is not None:
                yield event

    @property
    def unhandled_event_types(self) -> list:
        # The state is created per ``start`` call; this property is provided
        # for callers that wrap a single ``start`` iteration.
        return []  # pragma: no cover - convenience accessor


def _live_iter(
    *, dsn: str, slot_name: str, publication_name: str, start_lsn: str
) -> Iterable[bytes]:  # pragma: no cover - requires live PG; integration test
    from omnix.dm.d5_change_data_capture.pg_adapter.connection import (
        ensure_publication,
        ensure_slot,
        open_replication_connection,
    )

    conn = open_replication_connection(dsn)
    ensure_publication(conn, publication_name)
    ensure_slot(conn, slot_name)
    cur = conn.cursor()
    options = {
        "proto_version": "1",
        "publication_names": publication_name,
    }
    cur.start_replication(
        slot_name=slot_name,
        decode=False,
        options=options,
    )
    while True:
        msg = cur.read_message()
        if msg is None:
            continue
        yield msg.payload


def _factory(dsn: Any) -> PGAdapter:
    return PGAdapter(dsn)


register_adapter("postgres", _factory)


__all__ = ["PGAdapter"]
