"""Filesystem watch with .gitignore / .omnixignore and standard directory skips."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from omnix.find_bugs.walker import _load_gitignore, _path_matches_prefix, _skip_dir_name
from omnix.studio.paths import project_omnix_dir

_LOG = logging.getLogger("omnix.studio.watcher")

_STD_IGNORE_DIR_PARTS: frozenset[str] = frozenset(
    {
        ".git",
        ".omnix",
        "node_modules",
        ".next",
        "dist",
        "build",
        ".venv",
        "venv",
        "__pycache__",
    }
)


def _bad_file_suffixes(name: str) -> bool:
    low = name.lower()
    if name in (".DS_Store", "Thumbs.db", "thumbs.db", ".ds_store") or low == ".ds_store":
        return True
    for suf in (".pyc", ".pyo", ".swp", ".swo", ".swn", ".pyd"):
        if low.endswith(suf):
            return True
    if name.endswith("~") and not name.startswith(("#", ".#")):
        return True
    return False


def load_omnixignore(root: Path) -> list[str]:
    p = project_omnix_dir(root) / ".omnixignore"
    if not p.is_file():
        return []
    out: list[str] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        t = t.split("#", 1)[0].strip().rstrip("/")
        if t:
            out.append(t)
    return out


def is_studio_ignored(root: Path, relp: str) -> bool:
    """True if *relp* (posix) should be hidden from Studio (matches watcher + API list)."""
    root = root.resolve()
    p = Path(relp)
    gignore = _load_gitignore(root)
    oignore = load_omnixignore(root)
    for part in p.parts:
        if part in _STD_IGNORE_DIR_PARTS or _skip_dir_name(part):
            return True
    if _path_matches_prefix(p, gignore) or _path_matches_prefix(p, oignore):
        return True
    if p.name and _bad_file_suffixes(p.name):
        return True
    return False


class _Handler(FileSystemEventHandler):
    def __init__(self, root: Path, on_event: Callable[[str, str], None]) -> None:
        self._root = root.resolve()
        self._on = on_event
        self._gignore: list[str] = _load_gitignore(self._root)
        self._oignore: list[str] = load_omnixignore(self._root)
        self._gignore_mtime: float = self._gignore_file_mtime()
        self._lock = threading.Lock()

    def _gignore_file_mtime(self) -> float:
        p = self._root / ".gitignore"
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    def _refresh_if_needed(self) -> None:
        mt = self._gignore_file_mtime()
        with self._lock:
            if mt > self._gignore_mtime + 1e-9:
                self._gignore = _load_gitignore(self._root)
                self._gignore_mtime = mt
        oi = project_omnix_dir(self._root) / ".omnixignore"
        if oi.is_file():
            self._oignore = load_omnixignore(self._root)

    def _rel(self, path: str) -> str | None:
        try:
            return Path(path).resolve().relative_to(self._root).as_posix()
        except ValueError:
            return None

    def _ok_path(self, full: str) -> bool:
        self._refresh_if_needed()
        r = self._rel(full)
        if not r:
            return False
        pth = Path(r)
        for part in pth.parts:
            if part in _STD_IGNORE_DIR_PARTS or _skip_dir_name(part):
                return False
        if _path_matches_prefix(pth, self._gignore) or _path_matches_prefix(
            pth, self._oignore
        ):
            return False
        if pth.name and _bad_file_suffixes(pth.name):
            return False
        return True

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if not self._ok_path(str(event.src_path)):
            return
        r = self._rel(str(event.src_path))
        if not r:
            return
        _LOG.debug("watcher: path=%s event_type=%s", r, event.event_type)
        self._on(r, event.event_type)


class ProjectWatcher:
    """Watch *root*; ``on_event(relposix, event_type)`` (debounce in :class:`ParserBridge`)."""

    def __init__(
        self,
        root: str,
        on_event: Callable[[str, str], None],
    ) -> None:
        self._root = Path(root).resolve()
        self._on = on_event
        self._obs = Observer()
        self._h = _Handler(self._root, on_event)
        self._obs.schedule(self._h, str(self._root), recursive=True)

    def start(self) -> None:
        self._obs.start()

    def stop(self) -> None:
        self._obs.stop()
        self._obs.join(timeout=5.0)
