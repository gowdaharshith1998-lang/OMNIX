"""Layer 1: filesystem hygiene via watchdog (inotify on Linux) — slice 17b round 2."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, Protocol

from omnix.scan.filesystem_hygiene import (
    compute_finding,
    path_allowed_under_roots,
    severity_for_path,
)
from omnix.scan.turboscan.hygiene_polling import start_polling_observer
from omnix.scan.turboscan.types import turboscan_state_dir

_LOG = logging.getLogger("omnix.scan.turboscan.hygiene")

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError as e:  # pragma: no cover
    Observer = None  # type: ignore[misc, assignment]
    FileSystemEventHandler = object  # type: ignore[misc, assignment]
    _LOG.debug("watchdog import failed: %s", e)


class ActiveCaseRegistry(Protocol):
    def current_case(self) -> tuple[str, str, str, int] | None:
        """Return (relpath, function_name, repro_cmd, lineno) or None."""


class TurboscanHygieneCoordinator:
    """Correlates filesystem events with active PBT cases (P17 — best-effort timestamps)."""

    def __init__(
        self,
        *,
        repo_root: Path,
        sandbox_roots: tuple[Path, ...],
        tmp_root: Path,
        registry: ActiveCaseRegistry,
        on_finding: Callable[[dict], None],
        reproduction_template: str,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.sandbox_roots = sandbox_roots
        self.tmp_root = tmp_root.resolve()
        self.registry = registry
        self.on_finding = on_finding
        self.reproduction_template = reproduction_template
        self._lock = threading.Lock()
        self._seen_paths: set[str] = set()

    def handle_fs_event(self, kind: str, src_path: str) -> None:
        if kind not in ("created", "moved_to"):
            return
        try:
            p = Path(src_path).resolve()
        except OSError:
            return
        ps = str(p)
        turb_root = turboscan_state_dir(self.repo_root)
        try:
            p.relative_to(turb_root)
            return
        except ValueError:
            pass
        if path_allowed_under_roots(p, self.sandbox_roots):
            return
        with self._lock:
            if ps in self._seen_paths:
                return
            self._seen_paths.add(ps)
        cur = self.registry.current_case()
        if cur is None:
            return
        relp, fn, _, lineno = cur
        sev = severity_for_path(p, self.repo_root, self.tmp_root)
        try:
            sz = int(p.stat().st_size) if p.is_file() else 0
        except OSError:
            sz = 0
        hf = compute_finding(
            created_abs_paths=[ps],
            path_sizes={ps: sz},
            sandbox_roots=self.sandbox_roots,
            repo_root=self.repo_root,
            tmp_root=self.tmp_root,
            target_function=f"{relp}:{fn}",
            fuzz_inputs="(inotify)",
            reproduction=self.reproduction_template,
        )
        if hf is None:
            return
        d = hf.as_finding_dict()
        d["file"] = relp
        d["function"] = fn
        d["lineno"] = lineno
        self.on_finding(d)


if FileSystemEventHandler is object:

    class _InotifyHandler:  # type: ignore[no-redef]
        pass
else:

    class _InotifyHandler(FileSystemEventHandler):  # type: ignore[no-redef,misc,valid-type]
        def __init__(self, coord: TurboscanHygieneCoordinator) -> None:
            super().__init__()
            self._coord = coord

        def on_created(self, event):  # type: ignore[no-untyped-def]
            # Allow directory events: debt-19-class leaks (mkdir of `.omnix` etc.)
            # never produce a file event when the verify-subprocess runs in
            # delegated mode, so this watcher is the only signal we get.
            self._coord.handle_fs_event("created", event.src_path)

        def on_moved(self, event):  # type: ignore[no-untyped-def]
            dest = getattr(event, "dest_path", "") or ""
            self._coord.handle_fs_event("moved_to", dest)


class HygieneWatchSession:
    """R1: start watcher before PBT; R14: polling fallback."""

    def __init__(self, observer: object, coordinator: TurboscanHygieneCoordinator) -> None:
        self.observer = observer
        self.coordinator = coordinator

    def stop(self) -> None:
        try:
            self.observer.stop()  # type: ignore[union-attr]
            self.observer.join(timeout=5.0)  # type: ignore[union-attr]
        except Exception as e:
            _LOG.debug("hygiene observer stop: %s", e)


def start_hygiene_watcher(
    *,
    repo_root: Path,
    sandbox_roots: tuple[Path, ...],
    tmp_root: Path,
    registry: ActiveCaseRegistry,
    on_finding: Callable[[dict], None],
    reproduction_template: str,
    force_polling: bool = False,
) -> HygieneWatchSession:
    repo_root = repo_root.resolve()
    coord = TurboscanHygieneCoordinator(
        repo_root=repo_root,
        sandbox_roots=sandbox_roots,
        tmp_root=tmp_root,
        registry=registry,
        on_finding=on_finding,
        reproduction_template=reproduction_template,
    )
    watch_roots = [repo_root, tmp_root]
    handler_cb = coord.handle_fs_event

    if force_polling or Observer is None:
        obs = start_polling_observer(watch_roots, handler_cb)
        return HygieneWatchSession(obs, coord)

    try:
        observer = Observer()
        for r in watch_roots:
            if not r.is_dir():
                continue
            observer.schedule(_InotifyHandler(coord), str(r), recursive=True)
        observer.start()
        return HygieneWatchSession(observer, coord)
    except Exception as e:
        _LOG.warning("hygiene: native observer failed (%s); falling back", e)
        obs = start_polling_observer(watch_roots, handler_cb)
        return HygieneWatchSession(obs, coord)

