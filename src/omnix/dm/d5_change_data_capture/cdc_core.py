"""D5 core types + adapter registry.

The registry maps a ``dialect`` string to an adapter class. PR C ships:

  * ``postgres`` → ``omnix.dm.d5_change_data_capture.pg_adapter.adapter.PGAdapter``
    (live pgoutput logical-replication adapter)
  * ``oracle`` → ``OracleAdapter`` stub (raises ``NotYetImplementedInPRC`` on
    ``start()``; deferred to PR D)
  * ``mysql`` → ``MySQLAdapter`` stub (same)

Adapters implement the :class:`CDCAdapter` Protocol — ``start(slot_name,
publication_name)`` returns an iterable of :class:`omnix.dm._types.ChangeEvent`.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Protocol


class UnsupportedCDCDialect(RuntimeError):
    """Raised when ``get_adapter`` is called with a dialect the registry does
    not know about — Codex honesty (never silently return a no-op adapter)."""


class NotYetImplementedInPRC(NotImplementedError):
    """Raised by Oracle / MySQL adapter stubs at ``start()`` time. The message
    explicitly names PR D as the responsible PR so customers can correlate
    against the public roadmap."""


class CDCAdapter(Protocol):
    """Adapter contract. ``start(...)`` may be a generator that yields events
    until the caller signals shutdown (typically via SIGINT consumed by the
    replayer)."""

    def start(
        self, slot_name: str, publication_name: str
    ) -> Iterable[Any]:  # actually ChangeEvent
        ...


_REGISTRY: Dict[str, Callable[[Any], CDCAdapter]] = {}


def register_adapter(dialect: str, factory: Callable[[Any], CDCAdapter]) -> None:
    _REGISTRY[dialect] = factory


def get_adapter(dialect: str, dsn: Any) -> CDCAdapter:
    factory = _REGISTRY.get(dialect)
    if factory is None:
        raise UnsupportedCDCDialect(
            f"no D5 adapter registered for dialect {dialect!r}; "
            "supported: " + ", ".join(sorted(_REGISTRY)) or "(none yet)"
        )
    return factory(dsn)


def _eager_import_adapters() -> None:
    """Trigger registration of the bundled adapters. Importing the modules
    has the side-effect of calling :func:`register_adapter`."""
    from omnix.dm.d5_change_data_capture import (  # noqa: F401
        mysql_adapter,
        oracle_adapter,
    )
    try:
        from omnix.dm.d5_change_data_capture.pg_adapter import (  # noqa: F401
            adapter as _pg_adapter_module,
        )
    except Exception:
        # psycopg2 may be unavailable in some test envs; the registration is
        # best-effort. test_pg_connection.py mocks psycopg2 directly.
        pass


__all__ = [
    "UnsupportedCDCDialect",
    "NotYetImplementedInPRC",
    "CDCAdapter",
    "register_adapter",
    "get_adapter",
]
