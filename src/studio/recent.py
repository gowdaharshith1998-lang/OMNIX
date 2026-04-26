"""Read/write recent Studio projects: ``~/.omnix/recent.json`` (max 10)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.studio.paths import ensure_global_omnix_dir

_RECENT = "recent.json"
_VERSION = 1


@dataclass
class RecentEntry:
    path: str
    name: str
    last_opened_iso: str


def _path() -> Path:
    d = ensure_global_omnix_dir() / _RECENT
    return d


def _name_from_path(p: Path) -> str:
    try:
        return p.resolve().name or str(p)
    except OSError:
        return p.name or str(p)


def list_recent() -> list[dict[str, Any]]:
    f = _path()
    if not f.is_file():
        return []
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, dict) or raw.get("version") != _VERSION:
        return []
    out: list[dict[str, Any]] = []
    for e in raw.get("entries") or []:
        if not isinstance(e, dict):
            continue
        p, n, t = e.get("path"), e.get("name"), e.get("last_opened_iso")
        if not isinstance(p, str) or not isinstance(n, str) or not isinstance(t, str):
            continue
        out.append({"path": p, "name": n, "last_opened_iso": t})
    return out


def add_recent(path: str | os.PathLike[str], *, at_utc: datetime | None = None) -> None:
    """Prepend *path* (abs), dedupe by path, cap at 10, persist."""
    ap = os.path.realpath(path)
    p = Path(ap)
    now = (at_utc or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")
    cur = list_recent()
    new_entry = RecentEntry(path=ap, name=_name_from_path(p), last_opened_iso=now)
    # Dedupe: remove prior same path, then insert at 0
    pruned = [e for e in cur if e.get("path") != ap]
    out_list = [asdict(new_entry)] + pruned[:9]
    doc = {"version": _VERSION, "entries": out_list}
    dest = _path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
