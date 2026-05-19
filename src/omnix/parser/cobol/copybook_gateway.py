"""Thin context-managed gateway placeholder for JVM copybook tooling."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def start_copybook_gateway() -> Iterator[None]:
    """Lifecycle shim for future py4j gateway integration."""
    yield None
