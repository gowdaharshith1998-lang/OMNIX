"""Layer 1 fallback: watchdog PollingObserver (R14)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

_LOG = logging.getLogger("omnix.scan.turboscan.hygiene_poll")


class _PollHandler(FileSystemEventHandler):
    def __init__(self, on_event: Callable[[str, str], None]) -> None:
        super().__init__()
        self._on_event = on_event

    def on_created(self, event):  # type: ignore[no-untyped-def]
        self._on_event("created", event.src_path)

    def on_moved(self, event):  # type: ignore[no-untyped-def]
        dest = getattr(event, "dest_path", "") or ""
        self._on_event("moved_to", dest)


def start_polling_observer(
    watch_roots: list[Path],
    on_event: Callable[[str, str], None],
) -> PollingObserver:
    _LOG.warning("FALLBACK_POLLING: inotify fast path unavailable; using 250ms polling")
    obs = PollingObserver(timeout=0.25)
    for r in watch_roots:
        try:
            rr = r.resolve()
            if rr.is_dir():
                obs.schedule(_PollHandler(on_event), str(rr), recursive=True)
        except OSError as e:
            _LOG.debug("polling: skip watch %s: %s", r, e)
    obs.start()
    return obs
